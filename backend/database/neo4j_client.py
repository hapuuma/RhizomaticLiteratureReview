"""
V3: Neo4j Client — Database Layer
Optional persistence layer for the Rhizome Builder Agent.
Provides a lazy singleton connection to Neo4j.

Requires: pip install neo4j
Activate via environment: NEO4J_ENABLED=true, NEO4J_URI=bolt://localhost:7687,
                          NEO4J_USER=neo4j, NEO4J_PASSWORD=<password>
"""
from config import settings
from pipeline import logger

_driver = None


def get_neo4j_client():
    """
    Returns a live Neo4j driver, or None if Neo4j is not configured.
    Lazy singleton — connects on first call.
    """
    global _driver

    if not settings.neo4j_enabled or not settings.neo4j_uri:
        return None

    if _driver is not None:
        return _driver

    try:
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user or "neo4j", settings.neo4j_password or ""),
        )
        # Verify connectivity
        _driver.verify_connectivity()
        logger.info(f"Neo4j connected: {settings.neo4j_uri}")
        return _driver
    except ImportError:
        logger.warning("neo4j package not installed. Run: pip install neo4j")
        return None
    except Exception as exc:
        logger.error(f"Neo4j connection failed: {exc}")
        _driver = None
        return None


def close_neo4j_client():
    """Close the Neo4j driver connection."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None


def ensure_schema():
    """
    Create Neo4j schema constraints and indexes if they don't exist.
    Call once at startup if Neo4j is enabled.
    """
    client = get_neo4j_client()
    if client is None:
        return

    try:
        with client.session() as session:
            # Unique constraint on Paper id
            session.run(
                "CREATE CONSTRAINT paper_id IF NOT EXISTS "
                "FOR (p:Paper) REQUIRE p.id IS UNIQUE"
            )
            # Index on label for fast lookup
            session.run(
                "CREATE INDEX paper_label IF NOT EXISTS "
                "FOR (p:Paper) ON (p.label)"
            )
            # Index on is_rupture_node for Rupture Agent queries
            session.run(
                "CREATE INDEX paper_rupture IF NOT EXISTS "
                "FOR (p:Paper) ON (p.is_rupture_node)"
            )
        logger.info("Neo4j schema constraints verified.")
    except Exception as exc:
        logger.warning(f"Neo4j schema setup failed (non-critical): {exc}")
