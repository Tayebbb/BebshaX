"""Evaluation package for BebshaX persona quality and multi-model routing strategy benchmarks."""

from bebshax.evaluation.types import (
    EvaluationSuiteResult,
    OfflineEvalResult,
    PersonaMetricResult,
    StrategyMetricResult,
)
from bebshax.evaluation.persona_evaluator import PersonaEvaluator
from bebshax.evaluation.strategies import RoutingStrategy, StrategyRankerFactory
from bebshax.evaluation.routing_simulator import RoutingChaosSimulator
from bebshax.evaluation.offline_evaluator import OfflineEvaluator
from bebshax.evaluation.report_generator import ReportGenerator
from bebshax.evaluation.cross_route_consistency import CrossRouteReport, run_cross_route_eval

__all__ = [
    "CrossRouteReport",
    "EvaluationSuiteResult",
    "OfflineEvalResult",
    "PersonaMetricResult",
    "StrategyMetricResult",
    "PersonaEvaluator",
    "RoutingStrategy",
    "StrategyRankerFactory",
    "RoutingChaosSimulator",
    "OfflineEvaluator",
    "ReportGenerator",
    "run_cross_route_eval",
]
