import logging

from django.db import connection

from api.models import Person

logger = logging.getLogger(__name__)


class _Graph:
    """Minimal undirected graph used in place of networkx.Graph."""

    def __init__(self):
        self._adj: dict = {}

    def add_edge(self, u, v):
        if u not in self._adj:
            self._adj[u] = set()
        if v not in self._adj:
            self._adj[v] = set()
        self._adj[u].add(v)
        self._adj[v].add(u)

    def nodes(self):
        return list(self._adj.keys())

    def edges(self):
        seen: set = set()
        result = []
        for u, neighbors in self._adj.items():
            for v in neighbors:
                key = (min(u, v), max(u, v))
                if key not in seen:
                    seen.add(key)
                    result.append((u, v))
        return result


def build_social_graph(user):
    """Build co-appearance graph: nodes are named people, links weighted by shared photos."""
    try:
        link_query = """
            WITH face AS (
                SELECT DISTINCT ON (photo_id, person_id)
                    photo_id,
                    person_id,
                    api_person.name AS name
                FROM api_face
                JOIN api_person ON api_person.id = person_id
                JOIN api_photo ON api_photo.id = photo_id
                WHERE person_id IS NOT NULL
                    AND api_face.deleted = FALSE
                    AND api_photo.owner_id = %s
                ORDER BY
                    photo_id,
                    person_id,
                    CASE
                        WHEN classification_person_id = person_id
                            THEN classification_probability
                        ELSE 1.0
                    END DESC,
                    api_face.id
            )
            SELECT f1.name, f2.name, COUNT(DISTINCT f1.photo_id) AS weight
            FROM face f1
            JOIN face f2
                ON f1.photo_id = f2.photo_id
                AND f1.person_id < f2.person_id
            GROUP BY f1.name, f2.name
        """
        count_query = """
            WITH face AS (
                SELECT DISTINCT ON (photo_id, person_id)
                    photo_id,
                    person_id,
                    api_person.name AS name
                FROM api_face
                JOIN api_person ON api_person.id = person_id
                JOIN api_photo ON api_photo.id = photo_id
                WHERE person_id IS NOT NULL
                    AND api_face.deleted = FALSE
                    AND api_photo.owner_id = %s
                ORDER BY
                    photo_id,
                    person_id,
                    CASE
                        WHEN classification_person_id = person_id
                            THEN classification_probability
                        ELSE 1.0
                    END DESC,
                    api_face.id
            )
            SELECT name, COUNT(DISTINCT photo_id) AS photo_count
            FROM face
            GROUP BY name
        """
        with connection.cursor() as cursor:
            cursor.execute(link_query, [user.id])
            link_rows = cursor.fetchall()
            if not link_rows:
                return {"nodes": [], "links": []}

            cursor.execute(count_query, [user.id])
            photo_counts = {row[0]: int(row[1]) for row in cursor.fetchall()}

        names_in_graph: set[str] = set()
        links = []
        for source, target, weight in link_rows:
            names_in_graph.add(source)
            names_in_graph.add(target)
            links.append(
                {
                    "source": source,
                    "target": target,
                    "weight": int(weight),
                }
            )

        nodes = [
            {
                "id": name,
                "photo_count": photo_counts.get(name, 1),
            }
            for name in sorted(names_in_graph)
        ]
        return {"nodes": nodes, "links": links}
    except Exception:
        logger.exception(f"Error building social graph for user {user.id}")
        raise


def build_ego_graph(person_id):
    G = _Graph()
    person = Person.objects.prefetch_related("faces__photo__faces__person").filter(
        id=person_id
    )[0]
    for this_person_face in person.faces.all():
        for other_person_face in this_person_face.photo.faces.all():
            G.add_edge(person.name, other_person_face.person.name)
    nodes = [{"id": node} for node in G.nodes()]
    links = [{"source": pair[0], "target": pair[1]} for pair in G.edges()]
    res = {"nodes": nodes, "links": links}
    return res
