"""Parallelism detection for Quantrex Backtest."""

import dis
import warnings
from dataclasses import dataclass
from typing import Any, List, Optional, Set

from quantrex_core.logging import get_logger
from quantrex_core import InstrumentSpec

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ParallelismReport:
    """Report from parallelism detection analysis."""
    safe: bool
    reason: str
    independent_groups: List[List[str]]  # Groups of symbols that can run together
    warnings: List[str]


class ParallelismDetector:
    """Analyzes strategy bytecode to determine if parallel execution is safe.

    Detection is fully automatic - no decorator or manual opt-in required.
    Checks for cross-symbol access patterns that would make parallelism unsafe.
    """

    # Attributes/methods that indicate portfolio-level access
    PORTFOLIO_ATTRS = {'portfolio', 'positions'}
    CROSS_SYMBOL_METHODS = {'get_position', 'submit_order'}

    def __init__(self):
        self._symbol_names: Set[str] = set()

    def analyze(self, strategy: Any, instruments: List[InstrumentSpec]) -> ParallelismReport:
        """Analyze strategy for parallelism safety.

        Args:
            strategy: Strategy instance to analyze
            instruments: List of instrument specifications

        Returns:
            ParallelismReport with safety determination and grouping
        """
        self._symbol_names = {spec.symbol for spec in instruments}
        warnings_list = []
        unsafe_reasons = []

        # Get all methods to analyze
        methods_to_check = [
            'on_candle', 'on_start', 'on_stop', 'compute_indicators', '__init__'
        ]

        for method_name in methods_to_check:
            method = getattr(strategy.__class__, method_name, None)
            if method is None:
                continue

            # Skip base class implementations
            if method.__qualname__.startswith('Strategy.'):
                continue

            try:
                reason = self._analyze_method(method, method_name)
                if reason:
                    unsafe_reasons.append(f"{method_name}: {reason}")
            except Exception as e:
                warnings_list.append(f"Could not analyze {method_name}: {e}")

        # Check for symbol-keyed instance variables in __init__
        init_reason = self._check_init_symbol_state(strategy)
        if init_reason:
            unsafe_reasons.append(f"__init__: {init_reason}")

        if unsafe_reasons:
            return ParallelismReport(
                safe=False,
                reason="; ".join(unsafe_reasons),
                independent_groups=[],
                warnings=warnings_list,
            )

        # All instruments can run independently
        all_symbols = [spec.symbol for spec in instruments]
        return ParallelismReport(
            safe=True,
            reason="No cross-symbol dependencies detected",
            independent_groups=[all_symbols],  # Single group with all symbols
            warnings=warnings_list,
        )

    def _analyze_method(
        self,
        method: Any,
        method_name: str,
    ) -> Optional[str]:
        """Analyze a single method's bytecode for unsafe patterns."""
        try:
            bytecode = dis.Bytecode(method)
        except Exception:
            return None

        instructions = list(bytecode)

        # Check for attribute access: ctx.portfolio, ctx.positions, self.ctx.portfolio, etc.
        for i, instr in enumerate(instructions):
            if instr.opname == 'LOAD_ATTR' and instr.argval in self.PORTFOLIO_ATTRS:
                # Verify it's accessed via ctx or self.ctx
                if i > 0 and instructions[i-1].opname in ('LOAD_FAST', 'LOAD_DEREF'):
                    var_name = instructions[i-1].argval
                    if var_name in ('ctx', 'self'):
                        return f"accesses ctx.{instr.argval}"
                elif i > 1 and instructions[i-1].opname == 'LOAD_ATTR' and instructions[i-2].opname in ('LOAD_FAST', 'LOAD_DEREF'):
                    # self.ctx.portfolio pattern
                    if instructions[i-2].argval == 'self' and instructions[i-1].argval == 'ctx':
                        return f"accesses self.ctx.{instr.argval}"

        # Check for calls to get_position/submit_order with cross-symbol arguments
        CALL_OPNAMES = {'CALL_METHOD', 'CALL', 'CALL_KW'}

        for i, instr in enumerate(instructions):
            if instr.opname in CALL_OPNAMES:
                # Check if this is a call to get_position or submit_order
                method_name_called = None

                # Look backwards to find the method being called
                for j in range(i-1, max(-1, i-10), -1):
                    prev = instructions[j]
                    if prev.opname == 'LOAD_METHOD' and prev.argval in self.CROSS_SYMBOL_METHODS:
                        method_name_called = prev.argval
                        break
                    elif prev.opname == 'LOAD_ATTR' and prev.argval in self.CROSS_SYMBOL_METHODS:
                        method_name_called = prev.argval
                        break

                if method_name_called is None:
                    continue

                # Look for literal symbol arguments
                for j in range(i-1, max(-1, i-15), -1):
                    arg_instr = instructions[j]

                    # Case 1: Literal symbol string (LOAD_CONST)
                    if arg_instr.opname == 'LOAD_CONST' and isinstance(arg_instr.argval, str):
                        if arg_instr.argval in self._symbol_names:
                            # Check if this literal is actually candle.symbol
                            is_candle_symbol = False
                            if j > 1:
                                if (instructions[j-1].opname == 'LOAD_ATTR' and
                                    instructions[j-1].argval == 'symbol' and
                                    instructions[j-2].opname in ('LOAD_FAST', 'LOAD_DEREF') and
                                    instructions[j-2].argval == 'candle'):
                                    is_candle_symbol = True

                            if not is_candle_symbol:
                                return f"calls {method_name_called} with literal symbol '{arg_instr.argval}'"

                    # Case 2: candle.symbol access (LOAD_ATTR 'symbol' from 'candle')
                    elif arg_instr.opname == 'LOAD_ATTR' and arg_instr.argval == 'symbol':
                        if j > 0:
                            prev_instr = instructions[j-1]
                            if prev_instr.opname in ('LOAD_FAST', 'LOAD_DEREF') and prev_instr.argval == 'candle':
                                # This is the safe pattern: candle.symbol
                                pass
                            else:
                                # symbol attribute from something other than candle - suspicious
                                return f"calls {method_name_called} with non-candle symbol attribute"

        return None

    def _check_init_symbol_state(self, strategy: Any) -> Optional[str]:
        """Check __init__ for symbol-keyed instance variables."""
        init_method = getattr(strategy.__class__, '__init__', None)
        if init_method is None or init_method.__qualname__.startswith('Strategy.'):
            return None

        try:
            bytecode = dis.Bytecode(init_method)
        except Exception:
            return None

        # Look for patterns like: self.by_symbol = {} or self.positions = {}
        # where the dict is later keyed by symbol
        for instr in bytecode:
            if instr.opname == 'STORE_ATTR':
                attr_name = instr.argval
                # Heuristic: attribute names suggesting symbol-keyed storage
                if any(keyword in attr_name.lower() for keyword in
                       ['by_symbol', 'per_symbol', 'symbol_', '_by_symbol', '_per_symbol']):
                    return f"creates symbol-keyed attribute '{attr_name}'"

        return None