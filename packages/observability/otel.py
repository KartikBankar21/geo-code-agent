import logging
import os
from contextlib import contextmanager

from opentelemetry import metrics, trace

_INITIALIZED = False


def init_telemetry(service_name: str, app=None) -> None:
    """
    Initialize OpenTelemetry Traces, Metrics, and Logs exporting via OTLP/HTTP
    (e.g., Grafana Cloud). Safely becomes a no-op if OTEL_EXPORTER_OTLP_ENDPOINT
    is not configured.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
    if not endpoint:
        return

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    except ImportError:
        from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "geo-code-agent",
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "production"),
        }
    )

    # 1. Distributed Tracing -> Grafana Tempo
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    # 2. Metrics -> Grafana Mimir
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
        export_interval_millis=15000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # 3. Logs -> Grafana Loki (with automatic trace_id & span_id injection)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"))
    )
    LoggingInstrumentor().instrument(set_logging_format=True)
    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_handler)
    logging.getLogger().setLevel(logging.INFO)

    # Auto-instrument outbound `requests` (propagates W3C traceparent to Tier 3)
    RequestsInstrumentor().instrument()

    if app is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/health,/health")


def get_tracer(name: str = "geo-code-agent"):
    return trace.get_tracer(name)


def get_meter(name: str = "geo-code-agent"):
    return metrics.get_meter(name)


def inject_trace_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Inject active W3C traceparent/tracestate headers for cross-node calls."""
    from opentelemetry.propagate import inject

    carrier = dict(headers or {})
    inject(carrier)
    return carrier


@contextmanager
def traced_span(name: str, attributes: dict | None = None):
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)
        yield span