"""Static AST analyzer and abstract lineage engine (SPECIFICATION §8, §9, §13).

The analyzed source is parsed with :mod:`ast` and never executed, imported, or
passed to ``eval``/``exec``.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, replace
from typing import Any

from . import SCHEMA_VERSION, __version__, catalog
from .lineage import (
    PASS_THROUGH_METHODS,
    UNKNOWN_VALUE,
    BandFamily,
    ConstValue,
    Domain,
    ImageState,
    ImageValue,
    LogPending,
    ScaleState,
    Value,
    classify_bands,
    intersect_intervals,
    merge_envs,
    merge_values,
)
from .models import Coverage, Finding, InputInfo, Report
from .rules import landsat as landsat_rules
from .rules import scale as scale_rules
from .rules import sentinel1 as sentinel1_rules
from .rules import sentinel2 as sentinel2_rules
from .suppressions import parse_suppressions
from .temporal import parse_ee_date

__all__ = ["AnalysisError", "Analyzer", "analyze_source"]

#: Methods that yield a single image from a collection without altering pixel values.
#: Permitted as additional pass-throughs by SPECIFICATION §8.5 because they cannot
#: create a false positive scientific finding.
_ELEMENT_PASS_THROUGH = frozenset({"first", "mosaic"})


class AnalysisError(Exception):
    """Raised for input that cannot be analyzed (maps to CLI exit code 2)."""


@dataclass(frozen=True)
class ModuleValue:
    """A resolved module reference, e.g. the ``ee`` package."""

    name: str


@dataclass(frozen=True)
class FunctionValue:
    """A module-visible function definition usable as a ``.map()`` callback."""

    node: ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class LambdaValue:
    """A single-expression lambda usable as a ``.map()`` callback."""

    node: ast.Lambda


def _pos(node: ast.AST) -> tuple[int, int]:
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _is_literal_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _as_number(value: Value) -> float | None:
    if isinstance(value, ConstValue) and isinstance(value.value, (int, float)):
        if isinstance(value.value, bool):
            return None
        return float(value.value)
    return None


def _as_string(value: Value) -> str | None:
    if isinstance(value, ConstValue) and isinstance(value.value, str):
        return value.value
    return None


def _as_string_sequence(value: Value) -> tuple[str, ...] | None:
    if not isinstance(value, ConstValue):
        return None
    raw = value.value
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, tuple) and raw and all(isinstance(item, str) for item in raw):
        return tuple(raw)
    return None


class Analyzer:
    """Single-pass, statement-ordered abstract interpreter over a module AST."""

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self._findings: dict[Any, Finding] = {}
        self._recognized_datasets: set[tuple[int, int]] = set()
        self._operation_checks: set[tuple[str, int, int]] = set()
        self._unresolved_lineage: set[tuple[int, int]] = set()
        self._unresolved_temporal: set[tuple[int, int]] = set()
        self._analyzed_functions: set[int] = set()
        self._active_functions: set[int] = set()
        self._return_stack: list[list[Value]] = []

    # ------------------------------------------------------------------ driver

    def run(self) -> tuple[list[Finding], Coverage]:
        env: dict[str, Value] = {}
        self._exec_block(self.tree.body, env)
        self._sweep_unanalyzed_functions()

        coverage = Coverage(
            recognized_dataset_count=len(self._recognized_datasets),
            supported_operation_check_count=len(self._operation_checks),
            unresolved_lineage_count=len(self._unresolved_lineage),
            unresolved_temporal_scope_count=len(self._unresolved_temporal),
        )
        return list(self._findings.values()), coverage

    def _sweep_unanalyzed_functions(self) -> None:
        """Analyze functions never reached through ``.map()`` with unknown parameters.

        Lineage-dependent rules cannot fire there, but lineage-free checks such
        as EWL401 still apply.
        """
        pending = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and id(node) not in self._analyzed_functions
        ]
        pending.sort(key=_pos)
        for node in pending:
            if id(node) in self._analyzed_functions:
                continue
            env: dict[str, Value] = {arg.arg: UNKNOWN_VALUE for arg in self._all_args(node)}
            self._analyzed_functions.add(id(node))
            self._active_functions.add(id(node))
            self._return_stack.append([])
            try:
                self._exec_block(node.body, env)
            finally:
                self._return_stack.pop()
                self._active_functions.discard(id(node))

    @staticmethod
    def _all_args(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> list[ast.arg]:
        spec = node.args
        args = list(spec.posonlyargs) + list(spec.args) + list(spec.kwonlyargs)
        if spec.vararg is not None:
            args.append(spec.vararg)
        if spec.kwarg is not None:
            args.append(spec.kwarg)
        return args

    def _record(self, finding: Finding | None) -> None:
        if finding is None:
            return
        self._findings.setdefault(finding.dedup_key, finding)

    # -------------------------------------------------------------- statements

    def _exec_block(self, body: list[ast.stmt], env: dict[str, Value]) -> None:
        for stmt in body:
            self._exec_stmt(stmt, env)

    def _exec_stmt(self, node: ast.stmt, env: dict[str, Value]) -> None:
        if isinstance(node, ast.Assign):
            value = self._eval(node.value, env)
            for target in node.targets:
                self._bind(target, value, env)
            return

        if isinstance(node, ast.AnnAssign):
            value = self._eval(node.value, env) if node.value is not None else UNKNOWN_VALUE
            self._bind(node.target, value, env)
            return

        if isinstance(node, ast.AugAssign):
            self._eval(node.value, env)
            self._bind(node.target, UNKNOWN_VALUE, env)
            return

        if isinstance(node, ast.Expr):
            self._eval(node.value, env)
            return

        if isinstance(node, ast.Return):
            value = self._eval(node.value, env) if node.value is not None else UNKNOWN_VALUE
            if self._return_stack:
                self._return_stack[-1].append(value)
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            env[node.name] = FunctionValue(node)
            for decorator in node.decorator_list:
                self._eval(decorator, env)
            return

        if isinstance(node, ast.ClassDef):
            body_env = dict(env)
            self._exec_block(node.body, body_env)
            env[node.name] = UNKNOWN_VALUE
            return

        if isinstance(node, ast.If):
            self._eval(node.test, env)
            then_env = dict(env)
            self._exec_block(node.body, then_env)
            else_env = dict(env)
            self._exec_block(node.orelse, else_env)
            env.clear()
            env.update(merge_envs(then_env, else_env))
            return

        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._eval(node.iter, env)
            body_env = dict(env)
            self._bind(node.target, UNKNOWN_VALUE, body_env)
            self._exec_block(node.body, body_env)
            merged = merge_envs(env, body_env)
            self._exec_block(node.orelse, merged)
            env.clear()
            env.update(merged)
            return

        if isinstance(node, ast.While):
            self._eval(node.test, env)
            body_env = dict(env)
            self._exec_block(node.body, body_env)
            merged = merge_envs(env, body_env)
            self._exec_block(node.orelse, merged)
            env.clear()
            env.update(merged)
            return

        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                value = self._eval(item.context_expr, env)
                if item.optional_vars is not None:
                    self._bind(item.optional_vars, value, env)
            self._exec_block(node.body, env)
            return

        if isinstance(node, ast.Try):
            body_env = dict(env)
            self._exec_block(node.body, body_env)
            merged = body_env
            for handler in node.handlers:
                handler_env = dict(env)
                if handler.name:
                    handler_env[handler.name] = UNKNOWN_VALUE
                self._exec_block(handler.body, handler_env)
                merged = merge_envs(merged, handler_env)
            self._exec_block(node.orelse, merged)
            self._exec_block(node.finalbody, merged)
            env.clear()
            env.update(merged)
            return

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._exec_import(node, env)
            return

        # Anything else (assert, raise, delete, global, ...) still has its
        # expressions inspected so nested calls remain covered.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._eval(child, env)
            elif isinstance(child, ast.stmt):
                self._exec_stmt(child, env)

    def _exec_import(self, node: ast.Import | ast.ImportFrom, env: dict[str, Value]) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    # ``import ee as gee`` binds the alias to the imported module.
                    env[alias.asname] = ModuleValue(alias.name)
                else:
                    # ``import ee`` and ``import ee.batch`` both bind the root name.
                    root = alias.name.split(".")[0]
                    env[root] = ModuleValue(root)
            return
        # ``from x import y`` does not yield a module reference the analyzer models.
        for alias in node.names:
            env[alias.asname or alias.name] = UNKNOWN_VALUE

    def _bind(self, target: ast.expr, value: Value, env: dict[str, Value]) -> None:
        if isinstance(target, ast.Name):
            env[target.id] = value
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind(element, UNKNOWN_VALUE, env)
            return
        if isinstance(target, ast.Starred):
            self._bind(target.value, UNKNOWN_VALUE, env)
            return
        # Attribute / Subscript targets are not tracked; evaluate for coverage.
        self._eval(target, env)

    # ------------------------------------------------------------- expressions

    def _eval(self, node: ast.expr, env: dict[str, Value]) -> Value:
        if isinstance(node, ast.Constant):
            return ConstValue(node.value)

        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id == "ee":
                # Earth Engine is conventionally imported as ``ee``; recognising the
                # bare name lets fragments without the import still be analyzed.
                return ModuleValue("ee")
            return UNKNOWN_VALUE

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self._eval(element, env) for element in node.elts]
            if all(isinstance(item, ConstValue) for item in values):
                return ConstValue(tuple(item.value for item in values))  # type: ignore[union-attr]
            return UNKNOWN_VALUE

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, env)
            number = _as_number(operand)
            if number is not None:
                if isinstance(node.op, ast.USub):
                    return ConstValue(-number)
                if isinstance(node.op, ast.UAdd):
                    return ConstValue(number)
            return UNKNOWN_VALUE

        if isinstance(node, ast.BinOp):
            return self._eval_binop(node, env)

        if isinstance(node, ast.Call):
            return self._eval_call(node, env)

        if isinstance(node, ast.Attribute):
            base = self._eval(node.value, env)
            if isinstance(base, ModuleValue):
                return ModuleValue(f"{base.name}.{node.attr}")
            return UNKNOWN_VALUE

        if isinstance(node, ast.Lambda):
            return LambdaValue(node)

        if isinstance(node, ast.IfExp):
            self._eval(node.test, env)
            return merge_values(self._eval(node.body, env), self._eval(node.orelse, env))

        # Generic fallback: inspect nested expressions, resolve to UNKNOWN.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._eval(child, env)
        return UNKNOWN_VALUE

    def _eval_binop(self, node: ast.BinOp, env: dict[str, Value]) -> Value:
        left = self._eval(node.left, env)
        right = self._eval(node.right, env)

        if isinstance(node.op, ast.Mult):
            # ``10 * image.log10()`` and the commuted form (SPECIFICATION §10.4).
            for image_side, other_side, pattern in (
                (right, left, "10 * log10()"),
                (left, right, "log10() * 10"),
            ):
                if isinstance(image_side, ImageValue) and _as_number(other_side) == 10.0:
                    return self._apply_db_multiply(image_side.state, node, pattern)

        left_number = _as_number(left)
        right_number = _as_number(right)
        if left_number is not None and right_number is not None:
            return self._fold_numeric(node.op, left_number, right_number)

        if isinstance(left, ImageValue):
            return ImageValue(left.state.numerically_unknown())
        if isinstance(right, ImageValue):
            return ImageValue(right.state.numerically_unknown())
        return UNKNOWN_VALUE

    @staticmethod
    def _fold_numeric(op: ast.operator, left: float, right: float) -> Value:
        try:
            if isinstance(op, ast.Add):
                return ConstValue(left + right)
            if isinstance(op, ast.Sub):
                return ConstValue(left - right)
            if isinstance(op, ast.Mult):
                return ConstValue(left * right)
            if isinstance(op, ast.Div):
                return ConstValue(left / right)
            if isinstance(op, ast.Pow):
                return ConstValue(left**right)
        except (ZeroDivisionError, OverflowError, ValueError):
            return UNKNOWN_VALUE
        return UNKNOWN_VALUE

    # ------------------------------------------------------------------- calls

    def _eval_call(self, node: ast.Call, env: dict[str, Value]) -> Value:
        func = node.func

        if isinstance(func, ast.Attribute):
            receiver = self._eval(func.value, env)
            method = func.attr

            positional = [self._eval(arg, env) for arg in node.args]
            keywords = {
                kw.arg: self._eval(kw.value, env) for kw in node.keywords if kw.arg is not None
            }
            for kw in node.keywords:
                if kw.arg is None:
                    self._eval(kw.value, env)

            # EWL401 is a lineage-free explicitness check on the call itself.
            if method in scale_rules.SUPPORTED_REDUCTIONS:
                self._check_region_reduction(node, method)

            if (
                isinstance(receiver, ModuleValue)
                and receiver.name.split(".")[-1] == "ee"
                and method in ("Image", "ImageCollection")
            ):
                return self._construct_dataset(node, positional, method == "ImageCollection")

            if isinstance(receiver, ImageValue):
                return self._apply_image_method(
                    receiver.state, method, node, positional, keywords, env
                )

            return UNKNOWN_VALUE

        # Plain function call: arguments are inspected, result is unresolved.
        for arg in node.args:
            self._eval(arg, env)
        for kw in node.keywords:
            self._eval(kw.value, env)
        self._eval(func, env)
        return UNKNOWN_VALUE

    def _construct_dataset(
        self, node: ast.Call, positional: list[Value], is_collection: bool
    ) -> Value:
        if not positional:
            self._unresolved_lineage.add(_pos(node))
            return ImageValue(ImageState(is_collection=is_collection))

        first = positional[0]
        if isinstance(first, ImageValue):
            # e.g. ee.Image(collection.first()) — lineage flows through.
            state = first.state
            return ImageValue(
                replace(
                    state, is_collection=is_collection, pending_multiply=None, pending_log10=None
                )
            )

        dataset_id = _as_string(first)
        if dataset_id is None:
            self._unresolved_lineage.add(_pos(node))
            return ImageValue(ImageState(is_collection=is_collection))

        info = catalog.recognize_dataset(dataset_id)
        if info is None:
            # A statically known but unsupported dataset: identity is not usable
            # by any v0.1.0 rule.
            self._unresolved_lineage.add(_pos(node))
            return ImageValue(ImageState(is_collection=is_collection))

        self._recognized_datasets.add(_pos(node))
        return ImageValue(ImageState.from_dataset(info, is_collection=is_collection))

    # --------------------------------------------------------- image semantics

    def _apply_image_method(
        self,
        state: ImageState,
        method: str,
        node: ast.Call,
        positional: list[Value],
        keywords: dict[str, Value],
        env: dict[str, Value],
    ) -> Value:
        if method == "select":
            return ImageValue(self._apply_select(state, positional, node))

        if method == "filterDate":
            return ImageValue(self._apply_filter_date(state, positional))

        if method == "rename":
            return ImageValue(state.cleared(bands=None, band_family=BandFamily.UNKNOWN))

        if method in PASS_THROUGH_METHODS:
            return ImageValue(state.cleared())

        if method in _ELEMENT_PASS_THROUGH:
            return ImageValue(state.element())

        if method == "multiply":
            return ImageValue(self._apply_multiply(state, positional, node))

        if method == "add":
            return ImageValue(self._apply_add(state, positional, node))

        if method == "log10":
            return ImageValue(
                state.cleared(
                    sr_scale=ScaleState.UNKNOWN,
                    st_scale=ScaleState.UNKNOWN,
                    domain=Domain.UNKNOWN,
                    pending_log10=LogPending(
                        dataset_id=state.dataset_id,
                        domain=state.domain,
                        source_ids=state.source_ids,
                    ),
                )
            )

        if method == "addBands":
            return ImageValue(self._apply_add_bands(state, node, positional, keywords))

        if method == "normalizedDifference":
            return ImageValue(self._apply_normalized_difference(state, positional, node))

        if method == "map":
            return self._apply_map(state, positional, node, env)

        if method == "expression":
            return ImageValue(
                state.numerically_unknown().cleared(bands=None, band_family=BandFamily.UNKNOWN)
            )

        # Unrecognised operation: numeric semantics and band mapping become
        # UNKNOWN so that no rule requiring them can fire (SPECIFICATION §8.6).
        return ImageValue(
            state.numerically_unknown().cleared(bands=None, band_family=BandFamily.UNKNOWN)
        )

    def _apply_select(
        self, state: ImageState, positional: list[Value], node: ast.Call
    ) -> ImageState:
        names: tuple[str, ...] | None
        if len(positional) == 1:
            names = _as_string_sequence(positional[0])
        elif positional and all(_as_string(item) is not None for item in positional):
            names = tuple(_as_string(item) for item in positional)  # type: ignore[misc]
        else:
            names = None

        if names is None:
            return state.cleared(bands=None, band_family=BandFamily.UNKNOWN)

        self._check_qa60_band_selection(state, names, node)

        if names == (catalog.SR_REGEX_SELECTOR,):
            # The exact ``SR_B.`` selector is recognised as the Landsat SR family
            # for the documented scaling idiom (SPECIFICATION §8.7).
            return state.cleared(bands=None, band_family=BandFamily.SR)

        return state.cleared(bands=names, band_family=classify_bands(names, state.platform))

    def _apply_filter_date(self, state: ImageState, positional: list[Value]) -> ImageState:
        if len(positional) != 2:
            # Single-argument or unsupported forms leave temporal scope unproven.
            return state.cleared(interval=None)

        start_text = _as_string(positional[0])
        end_text = _as_string(positional[1])
        if start_text is None or end_text is None:
            return state.cleared(interval=None)

        start = parse_ee_date(start_text)
        end = parse_ee_date(end_text)
        if start is None or end is None or start >= end:
            return state.cleared(interval=None)

        return state.cleared(interval=intersect_intervals(state.interval, (start, end)))

    def _apply_multiply(
        self, state: ImageState, positional: list[Value], node: ast.Call
    ) -> ImageState:
        factor = _as_number(positional[0]) if len(positional) == 1 else None

        if state.pending_log10 is not None and factor == 10.0:
            return self._apply_db_multiply(state, node, "log10().multiply(10)").state

        return state.numerically_unknown().cleared(pending_multiply=factor)

    def _apply_db_multiply(
        self, state: ImageState, node: ast.Call | ast.BinOp, pattern: str
    ) -> ImageValue:
        pending = state.pending_log10
        if pending is not None:
            line, column = _pos(node)
            self._operation_checks.add(("db_conversion", line, column))
            self._record(sentinel1_rules.check_db_conversion(pending, pattern, line, column))
        return ImageValue(state.numerically_unknown())

    def _apply_add(self, state: ImageState, positional: list[Value], node: ast.Call) -> ImageState:
        offset = _as_number(positional[0]) if len(positional) == 1 else None
        scale = state.pending_multiply

        if scale is None or offset is None:
            return state.numerically_unknown()

        constants = catalog.landsat_constants()
        is_sr = scale == constants.sr_scale and offset == constants.sr_offset
        is_st = scale == constants.st_scale and offset == constants.st_offset

        if not (is_sr or is_st):
            return state.numerically_unknown()

        if state.family == catalog.FAMILY_LANDSAT_C2_L2:
            line, column = _pos(node)
            self._operation_checks.add(("landsat_scale_transform", line, column))
            self._record(landsat_rules.check_scale_transform(state, scale, offset, line, column))

            if is_sr and state.band_family is BandFamily.SR:
                return state.cleared(
                    sr_scale=ScaleState.CORRECTLY_SCALED,
                    st_scale=ScaleState.UNKNOWN,
                    domain=Domain.UNKNOWN,
                )
            # SPECIFICATION §9.2 recognises correct ST scaling for a proven
            # ST_B10 selection.
            if is_st and state.band_family is BandFamily.ST and state.bands == ("ST_B10",):
                return state.cleared(
                    sr_scale=ScaleState.UNKNOWN,
                    st_scale=ScaleState.CORRECTLY_SCALED,
                    domain=Domain.UNKNOWN,
                )

        return state.numerically_unknown()

    def _apply_add_bands(
        self,
        state: ImageState,
        node: ast.Call,
        positional: list[Value],
        keywords: dict[str, Value],
    ) -> ImageState:
        overwrite_node: ast.expr | None = None
        for kw in node.keywords:
            if kw.arg == "overwrite":
                overwrite_node = kw.value
        if overwrite_node is None and len(node.args) >= 3:
            overwrite_node = node.args[2]

        overwrite_proven = isinstance(overwrite_node, ast.Constant) and overwrite_node.value is True
        if not overwrite_proven:
            # The original band's scale state MUST NOT be replaced (SPECIFICATION §9.4).
            return state.cleared()

        source = positional[0] if positional else keywords.get("srcImg", UNKNOWN_VALUE)
        if not isinstance(source, ImageValue) or source.state.dataset_id != state.dataset_id:
            return state.cleared(sr_scale=ScaleState.UNKNOWN, st_scale=ScaleState.UNKNOWN)

        other = source.state
        if other.band_family is BandFamily.SR:
            return state.cleared(sr_scale=other.sr_scale)
        if other.band_family is BandFamily.ST:
            return state.cleared(st_scale=other.st_scale)
        return state.cleared(sr_scale=ScaleState.UNKNOWN, st_scale=ScaleState.UNKNOWN)

    def _apply_normalized_difference(
        self, state: ImageState, positional: list[Value], node: ast.Call
    ) -> ImageState:
        bands: tuple[str, ...] | None = None
        if positional:
            candidate = _as_string_sequence(positional[0])
            if candidate is not None and len(candidate) == 2:
                bands = candidate
        elif state.bands is not None and len(state.bands) == 2:
            # Immediately known two-band receiver selection (SPECIFICATION §10.1).
            bands = state.bands

        line, column = _pos(node)
        self._operation_checks.add(("normalized_difference", line, column))
        if state.family == catalog.FAMILY_LANDSAT_C2_L2 and bands is None:
            self._unresolved_lineage.add((line, column))

        self._record(landsat_rules.check_normalized_difference(state, bands, line, column))

        return state.numerically_unknown().cleared(bands=None, band_family=BandFamily.UNKNOWN)

    def _check_qa60_band_selection(
        self, state: ImageState, names: tuple[str, ...], node: ast.Call
    ) -> None:
        """Evaluate EWL501/EWL502 for a proven Sentinel-2 QA60 band selection.

        Band identity must be *proven* (SPECIFICATION §10.6, §10.7), and the
        supported way to prove it is a tracked literal band selector
        (SPECIFICATION §8.7). A ``QA60`` string appearing anywhere else — a
        property name or a property value, for example — does not prove that the
        band is used, so it MUST NOT fire the rule (SPECIFICATION §8.1).
        """
        if state.family != catalog.FAMILY_SENTINEL2:
            return
        if catalog.QA60_BAND not in names:
            return

        line, column = _pos(node)
        self._operation_checks.add(("qa60_use", line, column))
        finding, temporal_unresolved = sentinel2_rules.check_qa60_use(state, line, column)
        self._record(finding)
        if temporal_unresolved:
            self._unresolved_temporal.add((line, column))

    def _check_region_reduction(self, node: ast.Call, method: str) -> None:
        scale_node: ast.expr | None = None
        crs_transform_node: ast.expr | None = None
        scale_present = False
        crs_transform_present = False

        for kw in node.keywords:
            if kw.arg == "scale":
                scale_node, scale_present = kw.value, True
            elif kw.arg == "crsTransform":
                crs_transform_node, crs_transform_present = kw.value, True

        # reduceRegion(reducer, geometry, scale, crs, crsTransform, ...)
        # reduceRegions(collection, reducer, scale, crs, crsTransform, ...)
        if not scale_present and len(node.args) >= 3:
            scale_node, scale_present = node.args[2], True
        if not crs_transform_present and len(node.args) >= 5:
            crs_transform_node, crs_transform_present = node.args[4], True

        scale_explicit = scale_present and not _is_literal_none(scale_node)
        crs_transform_explicit = crs_transform_present and not _is_literal_none(crs_transform_node)

        line, column = _pos(node)
        self._operation_checks.add(("region_reduction", line, column))
        self._record(
            scale_rules.check_region_reduction(
                method, scale_explicit, crs_transform_explicit, line, column
            )
        )

    # --------------------------------------------------------------- map/calls

    def _apply_map(
        self, state: ImageState, positional: list[Value], node: ast.Call, env: dict[str, Value]
    ) -> Value:
        element = state.element()
        callback = positional[0] if positional else UNKNOWN_VALUE

        result: Value = UNKNOWN_VALUE
        if isinstance(callback, LambdaValue):
            result = self._invoke_lambda(callback, element, env)
        elif isinstance(callback, FunctionValue):
            result = self._invoke_function(callback, element, env)
        else:
            self._unresolved_lineage.add(_pos(node))

        if isinstance(result, ImageValue):
            return ImageValue(
                replace(
                    result.state,
                    is_collection=True,
                    pending_multiply=None,
                    pending_log10=None,
                )
            )
        return ImageValue(ImageState(is_collection=True, interval=element.interval))

    def _invoke_lambda(
        self, callback: LambdaValue, element: ImageState, env: dict[str, Value]
    ) -> Value:
        params = list(callback.node.args.posonlyargs) + list(callback.node.args.args)
        if len(params) != 1:
            return UNKNOWN_VALUE
        local = dict(env)
        local[params[0].arg] = ImageValue(element)
        return self._eval(callback.node.body, local)

    def _invoke_function(
        self, callback: FunctionValue, element: ImageState, env: dict[str, Value]
    ) -> Value:
        func = callback.node
        if id(func) in self._active_functions:
            # Recursive map callbacks are not required by v0.1.0.
            return UNKNOWN_VALUE

        spec = func.args
        positional_params = list(spec.posonlyargs) + list(spec.args)
        required = len(positional_params) - len(spec.defaults)
        if required != 1 or not positional_params:
            return UNKNOWN_VALUE

        local = dict(env)
        for arg in self._all_args(func):
            local[arg.arg] = UNKNOWN_VALUE
        local[positional_params[0].arg] = ImageValue(element)

        self._analyzed_functions.add(id(func))
        self._active_functions.add(id(func))
        self._return_stack.append([])
        try:
            self._exec_block(func.body, local)
            returns = self._return_stack[-1]
        finally:
            self._return_stack.pop()
            self._active_functions.discard(id(func))

        if not returns:
            return UNKNOWN_VALUE
        result = returns[0]
        for extra in returns[1:]:
            result = merge_values(result, extra)
        return result


def analyze_source(data: bytes) -> Report:
    """Analyze raw source bytes and produce a complete, path-free report."""
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalysisError("input is not valid UTF-8") from exc

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown location"
        raise AnalysisError(f"Python syntax error at {location}: {exc.msg}") from exc

    findings, coverage = Analyzer(tree).run()

    suppressions = parse_suppressions(source)
    kept: list[Finding] = []
    suppressed = 0
    for finding in findings:
        if suppressions.suppresses(finding.code, finding.line):
            suppressed += 1
        else:
            kept.append(finding)
    coverage.suppressed_finding_count = suppressed

    kept.sort(key=lambda finding: finding.sort_key)

    return Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        catalog_version=catalog.CATALOG_VERSION,
        input=InputInfo(sha256=hashlib.sha256(data).hexdigest(), byte_length=len(data)),
        findings=kept,
        coverage=coverage,
        warnings=list(suppressions.warnings),
    )
