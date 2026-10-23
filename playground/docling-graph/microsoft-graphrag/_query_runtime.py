"""Query-specific provider contract; indexing provider remains frozen per run."""
from pydantic import BaseModel, ConfigDict, Field

import _providers


class MapPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    score: int = Field(ge=0, le=100)


class GlobalMapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[MapPoint]


class QueryRuntime(_providers.Runtime):
    def complete(self, messages, response_format=None, **kwargs):
        # Native Global Search requests JSON-object mode. Enforce the actual
        # native map schema rather than ignoring that request or trusting prose.
        if kwargs.pop("response_format_json_object", False):
            response_format = GlobalMapResponse
        return super().complete(messages, response_format=response_format, **kwargs)


def configure(folder, **limits):
    if _providers._RUNTIME is not None:
        _providers._RUNTIME.close()
    runtime = QueryRuntime(folder, **limits)
    _providers._RUNTIME = runtime
    _providers.register()
    return runtime
