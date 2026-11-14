def get_connector_class(connector_type: str):
    from apps.ingestion.models import FetchSource
    from .job_boards import AshbyConnector, GreenhouseConnector, WorkableConnector
    from .rss_connector import RSSConnector

    registry = {
        FetchSource.ConnectorType.RSS: RSSConnector,
        FetchSource.ConnectorType.GREENHOUSE: GreenhouseConnector,
        FetchSource.ConnectorType.ASHBY: AshbyConnector,
        FetchSource.ConnectorType.WORKABLE: WorkableConnector,
    }
    try:
        return registry[connector_type]
    except KeyError:
        raise ValueError(f"No connector registered for type '{connector_type}'")
