"""OTel explicito: Flask, chamadas HTTP, metricas de negocio e logs via Collector."""
import atexit
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure(app, name):
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    resource = Resource.create({"service.name": name, "service.namespace": "toggle-master",
                                "service.instance.id": os.getenv("HOSTNAME", name)})
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tp)
    mp = MeterProvider(resource=resource, metric_readers=[
        PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10000)])
    metrics.set_meter_provider(mp)
    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=lp))
    FlaskInstrumentor().instrument_app(app, excluded_urls=".*/health")
    RequestsInstrumentor().instrument()
    counter = metrics.get_meter("togglemaster").create_counter("toggle_http_requests")

    @app.after_request
    def record(response):
        from flask import request
        if request.path != "/health":
            counter.add(1, {"http_method": request.method, "status_code": str(response.status_code)})
            logging.getLogger(name).info("http_request method=%s status=%s", request.method, response.status_code)
        return response

    for provider in (tp, mp, lp):
        atexit.register(provider.shutdown)
