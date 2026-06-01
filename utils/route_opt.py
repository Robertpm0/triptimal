from math import radians, sin, cos, sqrt, atan2


def haversine(a, b):
    lat1, lon1 = a
    lat2, lon2 = b

    R = 6371  # km

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    lat1 = radians(lat1)
    lat2 = radians(lat2)

    h = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * R * atan2(sqrt(h), sqrt(1 - h))


def shortest_route(locations, start, end):

    # Remove only ONE instance of start and end
    remaining = locations.copy()

    remaining.remove(start)
    remaining.remove(end)

    route = [start]
    leg_distances = []

    current = start

    # Greedy nearest-neighbor search
    while remaining:

        nearest = min(
            remaining,
            key=lambda loc: haversine(current, loc)
        )

        dist = haversine(current, nearest)

        leg_distances.append(dist)

        route.append(nearest)

        remaining.remove(nearest)

        current = nearest

    # Finally go to end
    final_dist = haversine(current, end)

    leg_distances.append(final_dist)

    route.append(end)

    return route, leg_distances