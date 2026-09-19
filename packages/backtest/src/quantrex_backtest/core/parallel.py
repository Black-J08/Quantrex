"""Parallel execution infrastructure for Quantrex Backtest.

Provides automatic parallelism detection via static bytecode analysis
and process-based parallel execution for independent instruments.
"""

import dis
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, TYPE_CHECKING

from quantrex_core import InstrumentSpec, PortfolioConfig, Strategy
from quantrex_core.logging import get_logger
from quantrex_backtest.portfolio import PortfolioResult

if TYPE_CHECKING:
    from quantrex_backtest import BacktestEngine

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
    
    @staticmethod
    def analyze(strategy: Strategy, instruments: List[InstrumentSpec]) -> ParallelismReport:
        """Analyze strategy for parallelism safety.
        
        Args:
            strategy: Strategy instance to analyze
            instruments: List of instruments in the backtest
            
        Returns:
            ParallelismReport with safety determination and grouping
        """
        warnings = []
        symbol_names = {spec.symbol for spec in instruments}
        
        # Get all methods to analyze
        methods_to_check = [
            'on_candle', 'on_start', 'on_stop', 'compute_indicators', '__init__'
        ]
        
        unsafe_reasons = []
        
        for method_name in methods_to_check:
            method = getattr(strategy.__class__, method_name, None)
            if method is None:
                continue
                
            # Skip base class implementations
            if method.__qualname__.startswith('Strategy.'):
                continue
                
            try:
                reason = ParallelismDetector._analyze_method(
                    method, method_name, symbol_names
                )
                if reason:
                    unsafe_reasons.append(f"{method_name}: {reason}")
            except Exception as e:
                warnings.append(f"Could not analyze {method_name}: {e}")
        
        # Check for symbol-keyed instance variables in __init__
        init_reason = ParallelismDetector._check_init_symbol_state(strategy)
        if init_reason:
            unsafe_reasons.append(f"__init__: {init_reason}")
        
        if unsafe_reasons:
            return ParallelismReport(
                safe=False,
                reason="; ".join(unsafe_reasons),
                independent_groups=[],
                warnings=warnings,
            )
        
        # All instruments can run independently
        all_symbols = [spec.symbol for spec in instruments]
        return ParallelismReport(
            safe=True,
            reason="No cross-symbol dependencies detected",
            independent_groups=[all_symbols],  # Single group with all symbols
            warnings=warnings,
        )
    
    @staticmethod
    def _analyze_method(
        method: Any, 
        method_name: str, 
        symbol_names: Set[str]
    ) -> Optional[str]:
        """Analyze a single method's bytecode for unsafe patterns."""
        try:
            bytecode = dis.Bytecode(method)
        except Exception:
            return None
        
        instructions = list(bytecode)
        
        # Check for attribute access: ctx.portfolio, ctx.positions, self.ctx.portfolio, etc.
        for i, instr in enumerate(instructions):
            if instr.opname == 'LOAD_ATTR' and instr.argval in ParallelismDetector.PORTFOLIO_ATTRS:
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
        # These can be CALL_METHOD, CALL, or CALL_KW
        CALL_OPNAMES = {'CALL_METHOD', 'CALL', 'CALL_KW'}
        
        for i, instr in enumerate(instructions):
            if instr.opname in CALL_OPNAMES:
                # Check if this is a call to get_position or submit_order
                # The method name would have been loaded via LOAD_METHOD or LOAD_ATTR before
                method_name_called = None
                
                # Look backwards to find the method being called
                for j in range(i-1, max(-1, i-10), -1):
                    prev = instructions[j]
                    if prev.opname == 'LOAD_METHOD' and prev.argval in ParallelismDetector.CROSS_SYMBOL_METHODS:
                        method_name_called = prev.argval
                        break
                    elif prev.opname == 'LOAD_ATTR' and prev.argval in ParallelismDetector.CROSS_SYMBOL_METHODS:
                        method_name_called = prev.argval
                        break
                
                if method_name_called is None:
                    continue
                
                # Now trace the arguments to find the symbol argument
                # For submit_order(symbol, side, quantity, order_type=...), symbol is first positional arg
                # For get_position(symbol), symbol is first positional arg
                # We need to find the first positional argument after the method
                
                # Look backwards from the call to find the symbol argument
                # The stack before call: [..., ctx, method, arg1, arg2, ...]
                # We scan backwards to find the first argument (symbol)
                
                # For CALL_KW, there's a tuple of keyword names at the top
                # For CALL, all args are positional
                # For CALL_METHOD, similar to CALL but method is on stack
                
                # Simple heuristic: look for LOAD_CONST with symbol name in the vicinity
                # of the call (within ~10 instructions back)
                for j in range(i-1, max(-1, i-15), -1):
                    arg_instr = instructions[j]
                    
                    # Case 1: Literal symbol string (LOAD_CONST)
                    if arg_instr.opname == 'LOAD_CONST' and isinstance(arg_instr.argval, str):
                        if arg_instr.argval in symbol_names:
                            # Check if this literal is actually candle.symbol by looking further back
                            # candle.symbol pattern: LOAD_FAST 'candle' -> LOAD_ATTR 'symbol'
                            is_candle_symbol = False
                            if j > 1:
                                # Check if previous instruction is LOAD_ATTR 'symbol' from 'candle'
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
    
    @staticmethod
    def _check_init_symbol_state(strategy: Strategy) -> Optional[str]:
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


def _run_single_instrument_backtest(
    instrument: InstrumentSpec,
    strategy_class: type[Strategy],
    strategy_init_kwargs: Dict[str, Any],
    config: PortfolioConfig,
    backtest_start_utc: datetime,
) -> PortfolioResult:
    """Run backtest for a single instrument in a worker process.
    
    This function must be at module level for multiprocessing pickling.
    Runs sequentially (no parallel) to avoid recursive parallelism.
    
    Args:
        instrument: Single instrument to backtest
        strategy_class: Strategy class (not instance) to instantiate
        strategy_init_kwargs: Keyword arguments for strategy __init__
        config: Portfolio configuration
        backtest_start_utc: Backtest start timestamp
        
    Returns:
        PortfolioResult for this single instrument
    """
    # Import here to avoid circular import
    from quantrex_backtest import BacktestEngine
    from quantrex_backtest.core.engine import BacktestEngine as EngineClass
    
    # Create a new engine with just this instrument
    # DataOrchestrator will be fast for single instrument (no cross-symbol sync needed)
    engine = EngineClass(
        instruments=[instrument],
        strategy=strategy_class(**strategy_init_kwargs),
        config=config,
    )
    
    # Run sequentially by calling _run_portfolio directly
    # Build staging dir
    staging_dir = engine._build_run_dir(backtest_start_utc, data_start=None, data_end=None)
    staging_dir.mkdir(parents=True, exist_ok=True)
    engine._ensure_run_log_file(staging_dir)
    
    return engine._run_portfolio(staging_dir, backtest_start_utc)


def _get_default_max_workers() -> int:
    """Get default worker count: half of available CPUs."""
    cpu_count = os.cpu_count() or 1
    return max(1, cpu_count // 2)


def run_parallel_backtest(
    engine: "BacktestEngine",
    staging_dir: Path,
    backtest_start_utc: datetime,
    max_workers: Optional[int] = None,
) -> PortfolioResult:
    """Run backtest in parallel for independent instruments.
    
    This is the main entry point for parallel execution. It:
    1. Detects if parallelism is safe
    2. If safe, partitions instruments and runs in parallel
    3. If not safe, falls back to sequential execution
    
    Args:
        engine: BacktestEngine instance (already initialized)
        staging_dir: Staging directory for logs
        backtest_start_utc: Backtest start timestamp
        max_workers: Maximum worker processes (default: half CPU count)
        
    Returns:
        Combined PortfolioResult
    """
    # Access private attributes for analysis
    strategy = engine._strategy
    instruments = engine._instruments
    config = engine._config
    
    # Run parallelism detection
    report = ParallelismDetector.analyze(strategy, instruments)
    
    if not report.safe:
        logger.info("Parallel execution not safe: %s. Running sequentially.", report.reason)
        return engine._run_portfolio(staging_dir, backtest_start_utc)
    
    if not report.independent_groups:
        logger.info("No independent groups found. Running sequentially.")
        return engine._run_portfolio(staging_dir, backtest_start_utc)
    
    # No benefit to parallelizing a single instrument
    if len(instruments) <= 1:
        logger.info("Single instrument, running sequentially.")
        return engine._run_portfolio(staging_dir, backtest_start_utc)
    
    # Check if adapters are picklable (mock adapters in tests are not)
    # If not picklable, fall back to sequential
    try:
        import pickle
        for spec in instruments:
            pickle.dumps(spec.adapter)
    except (pickle.PicklingError, TypeError, AttributeError):
        logger.info("Adapters not picklable (likely test mocks). Running sequentially.")
        return engine._run_portfolio(staging_dir, backtest_start_utc)
    
    # Use default worker count if not specified
    if max_workers is None:
        max_workers = _get_default_max_workers()
    
    logger.info("Running parallel backtest with %d workers for %d instruments", 
                max_workers, len(instruments))
    
    # Get strategy init kwargs (assume default constructor for now)
    strategy_init_kwargs = {}
    
    # Run parallel workers
    results: List[PortfolioResult] = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks for each instrument
        future_to_symbol = {}
        for spec in instruments:
            future = executor.submit(
                _run_single_instrument_backtest,
                spec,
                strategy.__class__,
                strategy_init_kwargs,
                config,
                backtest_start_utc,
            )
            future_to_symbol[future] = spec.symbol
        
        # Collect results
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                result = future.result()
                results.append(result)
                logger.info("Completed backtest for %s", symbol)
            except Exception as e:
                logger.exception("Worker failed for %s: %s", symbol, e)
                raise
    
    # Combine results
    if not results:
        return PortfolioResult.empty(config.initial_cash)
    
    combined = results[0]
    for result in results[1:]:
        combined = combined.combine(result)
    
    logger.info("Parallel backtest completed: %d instruments", len(results))
    return combined