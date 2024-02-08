from pathlib import Path
from typing import Generator

import simplekml
from gql import Client, gql
from gql.transport.httpx import HTTPXTransport

LIST_REACHES_QUERY = gql(
    """
    query listReaches($page: Int!, $per_page: Int!) {
        reaches(first:$per_page, page:$page) {
            paginatorInfo {
                hasMorePages
            }
            data {
                id
                river
                section
                ploc
                tloc
                geom
                states {
                    shortkey
                }
                pois {
                    name
                    difficulty
                    character
                    rloc
                }
            }
        }
    }
"""
)


def get_reaches(client: Client) -> Generator[dict, None, None]:
    page = 0
    per_page = 250

    while True:
        response = client.execute(
            LIST_REACHES_QUERY, {"page": page, "per_page": per_page}
        )
        yield from response["reaches"]["data"]
        if not response["reaches"]["paginatorInfo"]["hasMorePages"]:
            break
        page += 1


def reach_to_kml(reach: dict) -> simplekml.Kml | None:
    if not reach["geom"]:
        return None
    
    kml = simplekml.Kml(name=f"{reach['river']} - {reach['section']}")
    kml.newlinestring(
        name=kml.document.name,
        coords=[
            (float(x), float(y))
            for x, y in [p.split(" ") for p in reach["geom"].split(",")]
        ],
        description=f"https://www.americanwhitewater.org/content/River/view/river-detail/{id}/main",
    )

    for poi in reach["pois"]:
        if not poi["rloc"]:
            continue

        name = poi["name"]
        if poi["difficulty"] != "N/A":
            name += f" ({poi['difficulty']})"

        # TODO set icon based on character
        kml.newpoint(
            name=name,
            coords=[poi["rloc"].split(" ")],
        )

    # TODO: check if there was a take-out and put-in POI and only include
    # these points if there wasn't.
    kml.newpoint(name="Put in", coords=[reach["ploc"].split(" ")])
    kml.newpoint(name="Take out", coords=[reach["tloc"].split(" ")])

    return kml


if __name__ == "__main__":
    transport = HTTPXTransport(
        url="https://www.americanwhitewater.org/graphql",
        headers={"user-agent": "github.com/jacobian/aww2kml"},
    )
    client = Client(transport=transport)
    for reach in get_reaches(client):
        if kml := reach_to_kml(reach):
            for state in filter(None, reach["states"]):
                dest = (
                    Path("data")
                    / state["shortkey"]
                    / f"{reach["river"]} - {reach['section']}.kml"
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                kml.save(str(dest))
