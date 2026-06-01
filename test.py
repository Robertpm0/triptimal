import requests

import pandas as pd
'''
algorithm:
for each city in cities to go to
    find routes < desired window time from takeoff loc to cities to go to
    best_n_prices= get_best_prices(routes in window  )
    for each city in cities to go to
        find routes < desired window time from takeoff loc to cities to go to
 


'''
d=pd.read_csv("airports.csv")
d=d[~d["iata_code"].isnull()]
print(d["iata_code"])
print(d.head())

r=requests.get("https://www.airportroutes.com/api/routes/?icao=KLAS")
jsn=r.json()
print(jsn)
data=jsn
# for line in r:
#     if line.json().get("distance")<1300:
#         print(line.get("source_icao"))
rows = []

for f in data.get("features", []):
    p = f.get("properties", {})
    g = f.get("geometry", {})
    coords = g.get("coordinates", [None, None])

    row = {
        "source_icao": p.get("source_icao"),
        "source_iata": p.get("source_iata"),
        "dest_icao": p.get("destination_icao"),
        "dest_iata": p.get("destination_iata"),
        "distance_km": p.get("distance"),
        "flight_count": p.get("flight_count"),
        "operator": p.get("operator_iata"),
        "last_seen": p.get("last_seen"),
        "src_lon": coords[0][0] if coords and coords[0] else None,
        "src_lat": coords[0][1] if coords and coords[0] else None,
        "dst_lon": coords[1][0] if coords and len(coords)>1 else None,
        "dst_lat": coords[1][1] if coords and len(coords)>1 else None,
    }

    rows.append(row)

df=pd.DataFrame(rows)
print(df.head())
print(len(df))
properDf=df[df['distance_km']<2250]
print(len(properDf))


from amadeus import Client, ResponseError

amadeus = Client(
    client_id="vFAnLBDXF7IGZI4TYSfau1WqikrAiLJ4",
    client_secret="LH6NEq7YBdStt2hP"
)

def cheapest_on_date(origin, dest, date):
    try:
        resp = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=date,
            adults=1,
            currencyCode="USD",
            max=1   # ← only cheapest
        )
        
        offers = resp.data
        if not offers:
            return None
        
        offer = offers[0]
        price = float(offer["price"]["total"])
        airline = offer["validatingAirlineCodes"][0]
        
        return {
            "date": date,
            "price": price,
            "airline": airline
        }
        
    except ResponseError as e:
        return None


from datetime import date, timedelta

def date_range(start, end):
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)

results = []

for d in date_range(date(2026,3,1), date(2026,3,15)):
    r = cheapest_on_date("LAS", "JFK", d)
    if r:
        results.append(r)

print(results)

cheapest = min(results, key=lambda x: x["price"])
print("Cheapest:", cheapest)

import pandas as pd

df = pd.DataFrame(results)
print(df.sort_values("price").head())
