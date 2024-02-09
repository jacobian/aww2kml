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
                class
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

POI_ICON_MAP = {
    "putin": "http://maps.google.com/mapfiles/kml/paddle/go.png",
    "takeout": "http://maps.google.com/mapfiles/kml/paddle/grn-square.png",
    "access": "http://maps.google.com/mapfiles/kml/paddle/red-circle.png",
    "portage": "http://maps.google.com/mapfiles/kml/paddle/pause.png",
    "hazard": "http://maps.google.com/mapfiles/kml/shapes/caution.png",
    "waterfall": "http://maps.google.com/mapfiles/kml/shapes/water.png",
    "playspot": "http://maps.google.com/mapfiles/kml/shapes/water.png",
    "rapid": "http://maps.google.com/mapfiles/kml/shapes/water.png",
    "other": "http://maps.google.com/mapfiles/kml/paddle/red-circle.png",
}


def get_reaches(client: Client) -> Generator[dict, None, None]:
    page = 0
    per_page = 250

    while True:
        response = client.execute(
            LIST_REACHES_QUERY, {"page": page, "per_page": per_page}
        )
        for reach in response["reaches"]["data"]:
            if reach["geom"]:
                yield reach
        if not response["reaches"]["paginatorInfo"]["hasMorePages"]:
            break
        page += 1


def add_reach_to_kml(reach: dict, container: simplekml.Container | None):
    kml.newlinestring(
        name=(
            f"{kml.document.name} ({reach['class']})"
            if reach["class"]
            else kml.document.name
        ),
        coords=[
            (float(x), float(y))
            for x, y in [p.split(" ") for p in reach["geom"].split(",")]
        ],
        description=f"https://www.americanwhitewater.org/content/River/view/river-detail/{id}/main",
    )

    has_put_in_poi = False
    has_take_out_poi = False

    for poi in reach["pois"]:
        # Ignore POIs without a location
        if not poi["rloc"]:
            continue

        name = poi["name"]

        # Append rapid rating if given
        if poi["difficulty"] != "N/A":
            name += f" ({poi['difficulty']})"

        try:
            character = poi["character"][0]
        except IndexError:
            character = "other"

        if character == "putin":
            has_put_in_poi = True
        if character == "takeout":
            has_take_out_poi = True

        p = kml.newpoint(
            name=name,
            coords=[poi["rloc"].split(" ")],
        )
        p.style.iconstyle.icon.href = POI_ICON_MAP[character]

    if not has_put_in_poi:
        p = kml.newpoint(name="Put in", coords=[reach["ploc"].split(" ")])
        p.style.iconstyle.icon.href = POI_ICON_MAP["putin"]
    if not has_take_out_poi:
        p = kml.newpoint(name="Take out", coords=[reach["tloc"].split(" ")])
        p.style.iconstyle.icon.href = POI_ICON_MAP["takeout"]


if __name__ == "__main__":
    transport = HTTPXTransport(
        url="https://www.americanwhitewater.org/graphql",
        headers={"user-agent": "github.com/jacobian/aww2kml"},
    )
    client = Client(transport=transport)
    for reach in get_reaches(client):
        kml = simplekml.Kml(name=f"{reach['river']} - {reach['section']}")
        add_reach_to_kml(reach, kml)
        for state in reach["states"]:
            if not state["shortkey"]:
                continue
            dest = (
                Path("data")
                / state["shortkey"]
                / reach["river"].replace("/", "-")
                / (reach["section"].replace("/", "-") + ".kml")
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            kml.save(str(dest))
