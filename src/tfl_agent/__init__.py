"""Python library for the auditable TFL Generation Agent MVP."""
from tfl_agent.session import TFLSession
from tfl_agent.agent.workflow import run_agent

__all__ = ["TFLSession", "run_agent", "TFLAgent"]


def __getattr__(name):
    if name == "TFLAgent":
        from tfl_agent.agent.unified_pipeline import TFLAgent
        return TFLAgent
    raise AttributeError(name)
