from itertools import groupby
from operator import itemgetter
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
                    name
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

LIST_STATES_QUERY = gql(
    """
    query listStates {
        states(aw_only: true, first:1000) {
            data {
                shortkey
                name
                num_rivers
            }
        }
    }
    """
)


def get_states(client) -> Generator[dict, None, None]:
    response = client.execute(LIST_STATES_QUERY)
    yield from (
        state
        for state in response["states"]["data"]
        if state["shortkey"] and state["num_rivers"] > 0
    )


POI_ICONS = {
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

POI_STYLES = {
    key: simplekml.Style(
        iconstyle=simplekml.IconStyle(
            icon=simplekml.Icon(href=value),
        ),
    )
    for key, value in POI_ICONS.items()
}

RIVER_STYLE = simplekml.Style(
    linestyle=simplekml.LineStyle(
        color=simplekml.Color.blue,
        width=3,
    ),
)


def get_reaches(client: Client) -> Generator[dict, None, None]:
    page = 0
    per_page = 100

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
    line = container.newlinestring(
        name=reach_name(reach),
        coords=[
            (float(x), float(y))
            for x, y in [p.split(" ") for p in reach["geom"].split(",")]
        ],
        description=f"https://www.americanwhitewater.org/content/River/view/river-detail/{reach['id']}/main",
    )
    line.style = RIVER_STYLE

    has_put_in_poi = False
    has_take_out_poi = False

    for poi in reach["pois"]:
        # Ignore POIs without a location
        if not poi["rloc"]:
            continue

        try:
            character = poi["character"][0]
        except IndexError:
            character = "other"

        if character == "putin":
            has_put_in_poi = True
        if character == "takeout":
            has_take_out_poi = True

        p = container.newpoint(
            name=poi_name(poi),
            coords=[poi["rloc"].split(" ")],
        )
        p.style = POI_STYLES[character]

    if not has_put_in_poi:
        p = container.newpoint(name="Put in", coords=[reach["ploc"].split(" ")])
        p.style = POI_STYLES["putin"]
    if not has_take_out_poi:
        p = container.newpoint(name="Take out", coords=[reach["tloc"].split(" ")])
        p.style = POI_STYLES["takeout"]


def poi_name(poi: dict) -> str:
    name = poi["name"]

    # Append rapid rating if given
    if poi["difficulty"] and poi["difficulty"] != "N/A":
        name += f" ({poi['difficulty']})"
    return name


def build_client() -> Client:
    transport = HTTPXTransport(
        url="https://www.americanwhitewater.org/graphql",
        headers={"user-agent": "github.com/jacobian/aww2kml"},
    )
    client = Client(transport=transport)
    return client


def reach_name(reach):
    return (
        f"{reach['section']} ({reach['class']})" if reach["class"] else reach["section"]
    )


def main():
    client = build_client()
    reaches = get_reaches(client)
    reaches = sorted(reaches, key=itemgetter("river"))
    reaches_by_river = groupby(reaches, key=itemgetter("river"))

    for river, river_reaches in reaches_by_river:
        kml = simplekml.Kml(name=river)
        states = set()
        for reach in river_reaches:
            folder = kml.newfolder(name=reach_name(reach))
            add_reach_to_kml(reach, folder)
            states.update(
                state["shortkey"] for state in reach["states"] if state["shortkey"]
            )

        for state in states:
            dest = Path("data") / state / (river.replace("/", "-") + ".kml")
            dest.parent.mkdir(parents=True, exist_ok=True)
            kml.save(str(dest))


if __name__ == "__main__":
    main()
