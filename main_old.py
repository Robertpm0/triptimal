from flask import Flask, render_template, request, jsonify
import difflib
import numpy as np
# from math import radians, sin, cos, sqrt, atan2
import pandas as pd
import requests
import pandas as pd
from shapely.geometry import Point
from amadeus import Client, ResponseError
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from datetime import date as dt_date
from datetime import datetime,timedelta
import datetime as dt
from urllib.parse import quote
import folium
from utils.route_opt import shortest_route
import difflib
from collections import defaultdict
import geopandas as gpd
'''
algorithm:
for each city in cities to go to
    find routes < desired window time from takeoff loc to cities to go to
    best_n_prices= get_best_prices(routes in window  )
    for each city in cities to go to
        find routes < desired window time from takeoff loc to cities to go to
 


'''

amadeus = Client(
    client_id="vFAnLBDXF7IGZI4TYSfau1WqikrAiLJ4",
    client_secret="LH6NEq7YBdStt2hP"
)
cities_df=pd.read_csv("worldcities.csv")
cities_df["screen_name"]=cities_df["city"]+"_"+cities_df["country"]+"_"+cities_df["admin_name"]
# print(cities_df.head())
ITEMS=cities_df['city_uid']=cities_df["city"]+"_"+cities_df["country"]+"_"+cities_df["id"].astype(str)+"_"+cities_df["admin_name"]
ITEMS=ITEMS.dropna()
ITEMS=ITEMS.values
app = Flask(__name__)
def get_flight_routes(going_from_icao,max_distance_km=None):
    r=requests.get(f"https://www.airportroutes.com/api/routes/?icao={going_from_icao}")#{going_from_icao}")
    jsn=r.json()
    data=jsn
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

    # df=df[df["source_IATA"]=="KLAS"]
    # print(df.head())
    # print(df["source_iata"])
    # print(df[df["source_iata"]==going_from_icao])
    
    # print(df["dest_iata"])
    # print(len(df))
    # desired_flights=df[df['distance_km']<max_distance_km]
    return df

class Route:
    def __init__(self,to,frm,price):
        self.to=to
        self.frm=frm
        self.price=price

    def __lt__(self,right):
        return self.price<right.price

class Flight_Possibilites:
    def __init__(self,to,frm):
        self.leaving_from=frm
        self.going_to=to
        self.routes=[]

    def add_route(self,route):
        self.routes.append(route)

    def get_routes(self):
        return self.routes,self.leaving_from,self.going_to

class Route_Container:
    def __init__(self,name,routes,to,frm,scr_name=None):
        self.actual_name=name
        self.to=to
        self.frm=frm
        self.routes=routes
        self.screen_name=scr_name
        
class Route_Cost:
    def __init__(self,actual_1,actual_2,route_1,route_2,best_price):
        self.route_name_actual_1=actual_1
        self.route_name_actual_2=actual_2
        self.route_1=route_1
        self.route_2=route_2
        self.best_price=best_price

    def __lt__(self,right):
        return self.best_price<right.best_price    

class Route_Cost_Container:
    def __init__(self,real_name1,real_name2):
        self.screen1=real_name1
        self.screen2=real_name2
        self.route_costs=[]
    def add_route(self,route):
        self.route_costs.append(route)
    def get_n_best(self,n):
        return sorted(self.route_costs)[:n]
class Unpriced_Routes:
    def __init__(self,from_iata,to_iata,dist_km,from_dist,to_dist,actual_name):
        self.going_from_iata=from_iata
        self.going_to_iata=to_iata
        self.desired_destination=actual_name
        self.distance_km=dist_km
        self.from_distance=from_dist
        self.to_distance=to_dist

class Dated_Routes:
    def __init__(self,route,price,date):
        self.route=route
        self.price=price
        self.date=date


class Flight_Optimizer:
    def __init__(self,to_flights,from_flights,t_names,frm_names):
        self.get_to_trips=to_flights
        self.get_away_from_trips=from_flights
        self.to_names=t_names # actual names of the place you are starting your vacation in 
        self.from_names=frm_names # actual name of place you leave your vacation from 
    



    def optimise(self,n_per_route,n_days):
        best_to=[]
        best_away=[]

        # loop all the trips you leave your vacation from 
        for travel_option,from_name in zip(self.get_away_from_trips,self.from_names):

            best_n_to_spots,frm,to=travel_option.get_routes() # flight possibilites object the iata code for the place leave from and place going to 
            best_routes=Route_Container(name=frm,routes=best_n_to_spots,to=to,frm=frm,scr_name=from_name)
            best_away.append(best_routes)
            # print("first append")
        # loop places you go to vacation at
        for travel_option,to_name in zip(self.get_to_trips,self.to_names):        
            best_n_away_spots,away,goto=travel_option.get_routes()
            best_routes=Route_Container(name=goto,routes=best_n_away_spots,to=goto,frm=away,scr_name=to_name)
            # print("second append")
            best_to.append(best_routes)
        all_best_costs=[]
        valid_routes=[]

        for spot in best_to:
            # print("actual")
            # print(spot.actual_name)
            # temp_route_organizer=Route_Cost_Container(spot.screen_name)
            for spot2 in best_away:
                temp_route_organizer=Route_Cost_Container(spot.screen_name,spot2.screen_name)

                for route in spot.routes:
                # print(len(spot.routes))

                    # print(spot2.actual_name)
                    # temp_route_organizer=Route_Cost_Container(spot.screen_name,spot2.screen_name)
                    # temp_route_organizer.add_spot2(spot2.screen)

                    for route2 in spot2.routes:
                        # print(route.date)
                        # print(route2.date)
                        if (n_days-1)<=abs((route2.date-route.date).days)<=(n_days+1):
                            # print(spot.actual_name)
                            # print("DATES")
                            # print(abs((route2.date-route.date).days))
                            # print(abs((route.date-route2.date).days))
                            # print(spot2.actual_name)
                            # print("________________")
                            # print("FOUND ROUTE")
                            total_cost=route.price+route2.price
                            # print("TOTAL PRICE",total_cost)
                            temp_trip=Route_Cost(spot.actual_name,spot2.actual_name,route,route2,best_price=total_cost)
                            temp_route_organizer.add_route(temp_trip)
                            # print("GOOD")
                            # all_best_costs.append(temp_trip)
                    valid_routes.append(temp_route_organizer)

        # print("len r",len(valid_routes))
        return valid_routes

# def cheapest_on_date(origin, dest, date):
#     try:
#         resp = amadeus.shopping.flight_offers_search.get(
#             originLocationCode=origin,
#             destinationLocationCode=dest,
#             departureDate=date,
#             adults=1,
#             currencyCode="USD",
#             max=1   # ← only cheapest
#         )
        
#         offers = resp.data
#         if not offers:
#             return None
        
#         offer = offers[0]
#         price = float(offer["price"]["total"])
#         airline = offer["validatingAirlineCodes"][0]
        
#         return {
#             "date": date,
#             "price": price,
#             "airline": airline
#         }
        
#     except ResponseError as e:
#         return None


from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor, as_completed
#     try:
#         resp = amadeus.shopping.flight_offers_search.get(
#             originLocationCode=route.going_from_iata,
#             destinationLocationCode=route.going_to_iata,
#             departureDate=date,
#             adults=1,
#             currencyCode="USD",
#             max=1
#         )

#         offers = resp.data
#         if not offers:
#             return None

#         offer = offers[0]

#         temp_dated_trip=Dated_Routes(route,float(offer["price"]["total"]),date)
#         return temp_dated_trip

#         # return {
#         #     "date": date,
#         #     "price": float(offer["price"]["total"]),
#         #     "airline": offer["validatingAirlineCodes"][0]
#         # }

#     except ResponseError as e:
#         print(e.code)
#         print(e.response())
        
#         return None


# from duffel_api import Duffel
# from duffel_api.http_client import ApiError

# 
# def cheapest_on_date(route, date):
# from duffel_api import Duffel
# from duffel_api.http_client import ApiError

# duffel = Duffel()  # assumes DUFFEL_API_KEY env var

# def __cheapest_on_date(route, date):
#     # print(date)
#     try:
#         slices = [
#             {
#                 "origin": route.going_from_iata,
#                 "destination": route.going_to_iata,
#                 "departure_date":date.strftime("%Y-%m-%d"),
#              } #str(date.isoformat() if hasattr(date, "isoformat") else date),            }
#         ]

#         offer_request = (
#             duffel.offer_requests.create()
#             .passengers([{"type": "adult"}])
#             .slices(slices)
#             .return_offers()
#             .execute()
#         )
#         try:
#             offers = offer_request.offers
#             if not offers:
#                 # print("none")
#                 return None

#             cheapest_offer = offers[0]  # Duffel returns cheapest first
#             price = float(cheapest_offer.total_amount)

#             temp_dated_trip = Dated_Routes(route, price, date)
#             # print("good")
#             return temp_dated_trip

        
#         except Exception as e:
#             # print("OTHER ERROR",e)
#             return None
#     except ApiError as e:
#         # print("Duffel error:", e)
#         return None


import requests
from datetime import date as dt_date


def cheapest_on_date(route, date):
    try:
        # Ensure Duffel ISO date string
        if isinstance(date, dt_date):
            date_str = date.isoformat()
        else:
            date_str = str(date)

        url = "https://api.duffel.com/air/offer_requests?return_offers=true"

        headers = {
            "Authorization": f"Bearer {DUFFEL_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Duffel-Version": "v2",
        }

        payload = {
            "data": {
                "slices": [
                    {
                        "origin": route.going_from_iata,
                        "destination": route.going_to_iata,
                        "departure_date": date_str,
                    }
                ],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()

        data = resp.json()["data"]
        offers = data.get("offers", [])

        if not offers:
            return None

        # Duffel returns cheapest-first
        cheapest = offers[0]
        price = float(cheapest["total_amount"])

        return Dated_Routes(route, price, date)

    except requests.RequestException as e:
        # print("Duffel HTTP error:", e)
        return None
    except Exception as e:
        # print("Duffel parse error:", e)
        return None

def diff_month(newest_date, oldest_date):
    return (newest_date.year - oldest_date.year) * 12 + newest_date.month - oldest_date.month
class All_Routes:
    def __init__(self,to,frm,rout):
        self.to=to
        self.frm=frm
        self.route=rout
all_flights=[]
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    options = Options()
    # options.add_argument("--headless=new")  # modern headless mode
    # options.add_argument("--disable-gpu")
    # options.add_argument("--window-size=1920,1080")

    # driver = webdriver.Chrome(options=options)
    # driver=webdriver.Chrome(options=options,service=Service("C:\chromedriver-win64\chromedriver.exe"))
    driver = webdriver.Chrome(options=options,service=Service(ChromeDriverManager().install()))

    # driver=webdriver.Chrome(options=options)
    return driver


# driver = get_driver()
def get_flight_price(route,date,end_date,psgr):
    # print("LEN_FLIGHTS",len(all_flights))    

    month_map={
        1:"January",
        2: "February",
        3:"March",
        4:"April",
        5:"May",
        6:"June",
        7:"July",
        8:"August",
        9:"September",
        10:"October",
        11:"November",
        12:"December"
    }
    # Ensure Duffel ISO date string
    if isinstance(date, dt_date):
        date_str = date.isoformat()
    else:
        date_str = str(date)
    all_routes=[]

    leaving_from=route.going_from_iata
    going_to=route.going_to_iata
    for route2 in all_flights:
        if route2.to==going_to and route2.frm==leaving_from:
            return route2.route
# driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20LAS%20to%20CMR%20on%202026-12-19%20one%20way")
    # driver= webdriver.Chrome(service=Service("C:\chromedriver-win64\chromedriver.exe"),hea)
    driver=get_driver()
#    driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20LAS%20to%20HEL%20on%20{date_str}%20one%20way")
    print(leaving_from)
    print(going_to)
    print("leaf")
    print("go")
    # driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20{leaving_from}%20to%20{going_to}%20on%20{date_str}%20one%20way")
    passengers = psgr

    driver.get(
        f"https://www.google.com/travel/flights?q="
        f"{passengers}%20passengers%20Flights%20from%20"
        f"{leaving_from}%20to%20{going_to}%20on%20"
        f"{date_str}%20one%20way"
    )
    start_month=date.month
    end_month=end_date.month
    if date.year!=end_date.year:
        end_year=end_date.year
    else:
        end_year=date.year
    time.sleep(8)
    # click calendar
    body_element = driver.find_element(By.TAG_NAME, "body")
    all_page_text = body_element.text
    # print(all_page_text)
    # print("AFDASD", driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[2]/div[2]/div/div[2]/div[3]/ul/li[1]/div/div[2]/div/div[7]/div").text)
    try:
        if going_to not in all_page_text or leaving_from not in all_page_text:
            return []
        driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[1]/div/div/div[1]/div/div[1]/div/input").click()
        time.sleep(8)
        cals=driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[2]/div[2]/div[2]/div[2]/div/div/div[1]/div")
        time.sleep(4)
        cals2=cals.find_elements(By.XPATH, '//*[@role="rowgroup"]')
    except:
        return []
    num_months=diff_month(end_date,date)
    curr_month =range(start_month,start_month+num_months+2)
    mo_idx=0
    num_days=abs((date-end_date).days)
    start=False
    curr_date=date
    # for c in cals2:
    #     print(c.text)
    # print(len(cals2))
    # print(curr_month)
    for calendar in cals2:#range(0,len(curr_month)):
        # calendar=cals2[mo_idx].text
        calendar=calendar.text
        # print(calendar)
        if start==False:
            if month_map[start_month] not in calendar:
                # print("skip")
                # mo_idx+=1
                continue
            # else:
            #     print("FOUND")

        # print(calendar.split("\n"))
        calendar_idx=1
        for day in calendar.split("\n"):
            # print("s",day)
            # if day ==calendar.split("\n")[-2]:
            #     if curr_date==end_date:

            #         temp=All_Routes(going_to,leaving_from,all_routes)
            #         all_flights.append(temp)
            #         print("good2",end_date)
            #         return all_routes
            #     break
            # print(day)
            # print("_____________")
            try:
                g=int(day)
                # print("GOOD")
                # curr_date=curr_date+timedelta(days=1)

            except:
                # print("FAIL")
                calendar_idx+=1
                continue
            # print(date.day)
            # print("DAYL:",day)
            if int(day) ==date.day:

                # print("active")
                start=True
            if start==True:
                if "$" in calendar.split("\n")[calendar_idx]:
                    curr_route=  Dated_Routes(route, float(calendar.split("\n")[calendar_idx].replace("$","").replace(",","")), curr_date)
                    all_routes.append(curr_route)
                    # print("FOUND",curr_date)
                    # print(float(calendar.split("\n")[calendar_idx].replace("$","").replace(",","")))
                
            calendar_idx+=1
            try:
                g=int(day)
                if start==True:
                    curr_date=curr_date+timedelta(days=1)
            except:
                pass
            if curr_date==end_date:
                temp=All_Routes(going_to,leaving_from,all_routes)
                all_flights.append(temp)
                # print("good")
                # print("LEN ROUT",len(all_routes))
                return all_routes
        # mo_idx+=1
    return all_routes

def cheapest_each_date_parallel(routes, dates,psgr, max_workers=2):
    results = []
    sd=[]
    ed=[]
    print("DATES!!!: ",dates)
    for date in dates:
        sd.append(date[0])
        ed.append(date[-1])
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(get_flight_price, routes, sd,ed,psgr):
                results.extend(result)
    # print("LEN REYSKTS",len(results))
    return results
    # return sorted(results, key=lambda x: x["date"])4

def get_flight_prices(frm,to,dates,n_best,is_going_to,max_distance_away,psgr):

    # get the routes
    # check if we are going to our vacation
    if is_going_to==True:
        going_to_routes=[]
        base_flight=Unpriced_Routes(frm,to,0,0,0,to)
        going_to_routes.append(base_flight)
    else:
        going_to_routes=[]
        base_flight=Unpriced_Routes(frm,to,0,0,0,frm)
        going_to_routes.append(base_flight)
    # if is_going_to==True:
    #     # get all routes from our take off spot
    #     frm_flights=get_flight_routes(frm)
        
    #     # print("FROM")
    #     # print("TO")
    #     print(frm)
    #     print(to)
    #     to_flights=get_flight_routes(to)
    #     going_to_routes=[]
    #     if len(to_flights)==0 or len(frm_flights)==0:
    #         print("no flights")
    #         return []
    #     frm=frm_flights["source_iata"].values[0]
    #     to=to_flights["source_iata"].values[0]
    #     # print("FRM",frm)
    #     # print("TO",to)
    #     idx=0
    #     if to in frm_flights["dest_iata"].values:

    #         base_data=frm_flights[frm_flights["dest_iata"]==to]
    #         base_flight=Unpriced_Routes(frm,to,base_data["distance_km"].values[0],base_data["distance_km"].values[0],0,to)
    #         going_to_routes.append(base_flight)
    #     to_flights=to_flights[to_flights["distance_km"]<=max_distance_away]
    #     for flight in frm_flights["dest_iata"]:

    #         if flight in to_flights["dest_iata"].values:
    #             to_flight=to_flights[to_flights["dest_iata"]==flight]
    #             curr_route=Unpriced_Routes(frm,flight,frm_flights["distance_km"].values[idx]+to_flight["distance_km"].values[0],frm_flights["distance_km"].values[idx],
    #                                        to_flight["distance_km"].values[0],to)
    #             going_to_routes.append(curr_route)
    #         idx+=1       
    
    # else:
    #     frm_flights=get_flight_routes(frm)
    #     to_flights=get_flight_routes(to)

    #     if len(to_flights)==0 or len(frm_flights)==0:
    #         # print("none found")
    #         # print(to_flights)
    #         # print(frm_flights)
    #         return []
    #     frm=frm_flights["source_iata"].values[0]
    #     to=to_flights["source_iata"].values[0]
    #     # print("FRM",frm)
    #     # print("TO",to)
    #     going_to_routes=[]

    #     idx=0
    #     if to in frm_flights["dest_iata"].values:

    #         base_data=frm_flights[frm_flights["dest_iata"]==to]
    #         base_flight=Unpriced_Routes(frm,to,base_data["distance_km"].values[0],base_data["distance_km"].values[0],0,frm)
    #         going_to_routes.append(base_flight)
    #     frm_flights=frm_flights[frm_flights["distance_km"]<=max_distance_away]
    #     for flight in frm_flights["dest_iata"]:

    #         if flight in to_flights["dest_iata"].values:
    #             to_flight=to_flights[to_flights["dest_iata"]==flight]
    #             curr_route=Unpriced_Routes(flight,to,frm_flights["distance_km"].values[idx]+to_flight["distance_km"].values[0],frm_flights["distance_km"].values[idx],
    #                                        to_flight["distance_km"].values[0],frm)
    #             going_to_routes.append(curr_route)
    #         idx+=1



# get the price
# 
# 
        # start = date(2024, 1, 1)
        # end = date(2024, 1, 10)
        # 
    start=dates[0]
    end=dates[1]
    # print(end)
    # print(start)
    results=[]
    dates = [start + timedelta(days=i)
    for i in range((end - start).days + 1)]    
    # print("LEN DATES",len(dates))
    # print(len(going_to_routes))
    # print()
    # print("_______________________________")
    all_dates=[dates]*len(going_to_routes)
    # print(len(all_dates))
    # print(dates)
    going_to_routes=going_to_routes
    # print(len(going_to_routes))

    results=cheapest_each_date_parallel(going_to_routes,all_dates,psgr)
    # for date in dates:
        # print("LEN ROUTE",len(going_to_routes))
        # for route in going_to_routes:
        #     print("r")
        #     r = cheapest_on_date(route.going_from_iata, route.going_to_iata, date)
        #     if r:
        #         print("got")
        #         temp_dated_trip=Dated_Routes(route,r["price"],date)
        #         results.append(temp_dated_trip)
    # print(len(results))
    print("done")
    results=[x for x in results if x is not None]
    print(len(results))
    return results 
def find_nearest_airports(lat, lng, gdf, n=6):
    target_point = gpd.GeoSeries([Point(lng, lat)], crs="EPSG:4326")

    # project to metric CRS
    gdf_m = gdf.to_crs(gdf.estimate_utm_crs())
    target_m = target_point.to_crs(gdf_m.crs).iloc[0]

    # distances to all airports
    dists = gdf_m.distance(target_m)

    # indices of n closest
    idxs = dists.nsmallest(n).index

    # return IATA codes (list)
    airports=gdf.loc[idxs, "iata_code"].tolist()
    new_airports1=[]
    new_airports2=[]
    new_airports3=[]
    new_airports4=[]
    new_airports5=[]

    for a in airports:
        if gdf[gdf["iata_code"]==a]["type"].values[0]=="international_airport":
            new_airports1.append(a)
        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="large_airport":
            new_airports2.append(a)
        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="medium_airport":
            new_airports3.append(a)
        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="small_airport":
            new_airports4.append(a)
        else:
            new_airports5.append(a)
    new_airports=new_airports1+new_airports2+new_airports3+new_airports4+new_airports5
    return new_airports[:3]

def optimal_find_trips(cities,keys,start_date,end_date,num_days,origin,passgr):
    # print("origin",origin)
    # print(len(cities_df))
    origin_data=cities_df[cities_df["id"]==int(origin)]
    # print(origin_data.head())
    df = pd.read_csv("airports.csv")
    df=df[~df["iata_code"].isnull()]
    # df=df[df["icao_code"].isnull()]

    gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df.longitude_deg, df.latitude_deg),
    crs="EPSG:4326"   # WGS84 lat/lon
    )
#     target_lat = origin_data.lat.values[0]
#     target_lon = origin_data.lng.values[0]
#     target_point = gpd.GeoSeries([Point(target_lon, target_lat)], crs="EPSG:4326")

#     gdf_m = gdf.to_crs(gdf.estimate_utm_crs())
#     target_m = target_point.to_crs(gdf_m.crs).iloc[0]

# # find closest row
#     closest_idx = gdf_m.distance(target_m).idxmin()
#     closest_row = gdf.loc[closest_idx]

    origin_iata=find_nearest_airports(origin_data.lat.values[0],origin_data.lng.values[0],gdf)
    start_date = datetime.strptime(start_date,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date,"%Y-%m-%d").date()
    retries=0
    while retries <3:
        # print("ORIGIN",origin_iata)
        for cty in origin_iata:
            all_flights=[]
            starting_city=cty# iata code
            to_cost=0

            max_arrival_date=end_date-timedelta(days=num_days)
            
            #iata code
            to_trips=[]
            from_trips=[]
            city_iata=[]
            actual_names=[]
            to_names=[]
            from_names=[]
            for key in keys:
                origin_data=cities_df[cities_df["id"]==int(key)]  
                curr_iata=find_nearest_airports(origin_data.lat.values[0],origin_data.lng.values[0],gdf)
                city_iata.extend(curr_iata)
                actual_names.extend([origin_data.screen_name.values[0]]*len(curr_iata))

            for arriv_city,actual_name in zip(city_iata,actual_names):
                # print(arriv_city)
                # print("start")
                # print(actual_name)
                min_n_flights=get_flight_prices(starting_city,arriv_city,[start_date,max_arrival_date],6,True,400,passgr)
                print("NUM FLIGHTS",len(min_n_flights))
                print("CITY: ",actual_name)
                curr_trip= Flight_Possibilites(to=arriv_city,frm=starting_city) 
                for flight in min_n_flights:
                    curr_trip.add_route(flight)
                # iata code
                to_trips.append(curr_trip)
                to_names.append(actual_name)
            for depart_city,actual_name in zip(city_iata,actual_names):
                # print("start back")
                # print(actual_name)
                min_depart_date=start_date+timedelta(days=num_days)
                min_flights_depart=get_flight_prices(depart_city,starting_city,[min_depart_date,end_date],6,False,400,passgr)
                # print("NUM FLIGHTS",len(min_flights_depart))

                curr_trip=Flight_Possibilites(to=starting_city,frm=depart_city)
                # print("TO",start)
                for flight in min_flights_depart:
                    curr_trip.add_route(flight)
                from_trips.append(curr_trip)
                from_names.append(actual_name)
            
            # print(len(to_trips))
            # print("LLLL")
            # print(len(from_trips))
            optimizer=Flight_Optimizer(to_flights=to_trips,from_flights=from_trips,t_names=to_names,frm_names=from_names)
            optimised_routes=optimizer.optimise(3,num_days)
            
            if len(optimised_routes)!=0:
                print("OPTIMISED ROUTES")
                retries=4
                return optimised_routes

                # break
        retries+=1
    return optimised_routes





# Example dataset


# ITEMS={}
@app.route("/")
def index():
    return render_template("index.html")

# @app.route("/search")
# def search():
#     query = request.args.get("q", "")
#     n = int(request.args.get("n", 5))  # number of nearest matches

#     if not query:
#         return jsonify([])

#     matches2 = difflib.get_close_matches(query, ITEMS, n=n, cutoff=0.4)
#     # matches=[{"id":x.split["_"][2] ,"name":f'{x.split["_"][0]}'+","+f'{x.split["_"][1]}'}for x in matches2 ]
#     matches = [
#     (lambda parts: {"id": parts[2], "name": f"{parts[0]},{parts[4]},{parts[1]}"})
#     (x.split("_"))
#     for x in matches2
# ]
#     return jsonify(matches)

# import difflib
# from collections import defaultdict
import time
@app.route("/search")
def search():
    n=3
    cutoff=0.4
    query = request.args.get("q", "")
    if not query:
        return jsonify([])

    query = query.lower().strip()

    # city -> list of full item strings
    city_map = defaultdict(list)
    for item in ITEMS:
        # print(item)
        parts = item.split("_")
        city = parts[0].lower()
        city_map[city].append(item)

    # fuzzy match only city names
    city_matches = difflib.get_close_matches(
        query,
        city_map.keys(),
        n=n,
        cutoff=cutoff
    )

    # flatten matched full items
    matches2 = [
        full
        for city in city_matches
        for full in city_map[city]
    ]

    # format results
    matches = [
        (lambda parts: {"id": parts[2], "name": f"{parts[0]},{parts[3]},{parts[1]}"})
        (x.split("_"))
        for x in matches2
    ]

    return matches

def get_cheapest_n_flights(optimal_trips, n=3):
    grouped = {}

    # Group trips by (departing_from, landing_in)
    for trip in optimal_trips:
        key = (trip.screen1, trip.screen2)

        if key not in grouped:
            grouped[key] = []

        # Collect all possible options for this route
        for option in trip.get_n_best(10):  # grab more, we’ll sort manually
            grouped[key].append(option)

    results = []

    # Now sort + trim each group
    for (departing, landing), options in grouped.items():
        # Sort cheapest → expensive
        sorted_options = sorted(options, key=lambda x: x.best_price)

        # Take top N
        best_n = sorted_options[:n]

        trip_data = {
            "n_best_count": len(best_n),
            "departing_from": departing,
            "landing_in": landing,
            "options": []
        }

        for n_trip in best_n:
            trip_data["options"].append({
                "route_name_actual_1": str(n_trip.route_name_actual_1),
                "route_name_actual_2": str(n_trip.route_name_actual_2),
                "best_price": float(n_trip.best_price),

                "route_1_date": str(n_trip.route_1.date),
                "route_2_date": str(n_trip.route_2.date),

                "route_1_going_from_iata": str(n_trip.route_1.route.going_to_iata),
                "route_2_going_to_iata": str(n_trip.route_2.route.going_from_iata),

                "route_1_distance_km": float(n_trip.route_1.route.distance_km),
                "route_2_distance_km": float(n_trip.route_2.route.distance_km),
            })

        results.append(trip_data)

    # Sort all route groups by cheapest option inside them
    results.sort(key=lambda trip: trip["options"][0]["best_price"] if trip["options"] else float("inf"))

    return results

def make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(i) for i in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    else:
        return obj
    

def build_map(routes):

    route_colors = {
        "plane": "blue",
        "train": "green",
        "taxi/car": "red"
    }

    # Start with temporary center
    m = folium.Map(location=[0, 0], zoom_start=2)

    all_points = []

    for route in routes:

        from_name, from_lat, from_lon = route["from"]
        to_name, to_lat, to_lon = route["to"]

        color = route_colors.get(route["type"], "gray")

        # Save coordinates
        all_points.append([from_lat, from_lon])
        all_points.append([to_lat, to_lon])

        # Markers
        folium.Marker(
            [from_lat, from_lon],
            popup=from_name
        ).add_to(m)

        folium.Marker(
            [to_lat, to_lon],
            popup=to_name
        ).add_to(m)

        # Route line
        folium.PolyLine(
            locations=[
                [from_lat, from_lon],
                [to_lat, to_lon]
            ],
            color=color,
            weight=5
        ).add_to(m)

    # AUTO CENTER + AUTO ZOOM
    m.fit_bounds(all_points)

    return m._repr_html_()

@app.route("/submit", methods=["POST"])
def submit():
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    nights = request.form.get("nights")

    cities = request.form.getlist("cities")
    city_ids = request.form.getlist("city_ids")

    # remove empty entries (unselected inputs)
    cities = [c for c in cities if c]
    city_ids = [c for c in city_ids if c]
    
    origin_city = request.form.get("origin_city")
    origin_city_id = request.form.get("origin_city_id")
    passengers=request.form.get("passengers")
    # Example: build trip request object
    trip = {
        "start_date": start_date,
        "end_date": end_date,
        "nights": int(nights),
        "cities": cities,
        "city_ids": city_ids
    }
    city_coords=[]
    coords_map={}
    for city in city_ids:
        city_data=cities_df[cities_df["id"]==int(city)]
        city_coords.append((city_data.lat.values[0],city_data.lng.values[0]))
        coords_map[(city_data.lat.values[0],city_data.lng.values[0])]=city_data.screen_name.values[0]
    # print(origin_city_id)  # replace with optimizer logic
    optimal_trips=optimal_find_trips(cities,city_ids,start_date,end_date,int(nights),origin_city_id,passengers)
    print(len(optimal_trips))
    print("START")
    # results=[]
    airports_df=pd.read_csv("airports.csv")
    grouped_routes = {}

    for trip in optimal_trips:
        print("loop")

        key = (trip.screen1, trip.screen2)

        if key not in grouped_routes:
            grouped_routes[key] = {
                "departing_from": trip.screen2,
                "landing_in": trip.screen1,
                "options": [],
                "seen_options": set()  # used for deduping
            }

        print("optimal")

        optimised_n_trips = trip.get_n_best(3)

        print("LEN: ", len(optimised_n_trips))

        maps = []

        for n_trip in optimised_n_trips:

            leaving_from = str(n_trip.route_1.route.going_to_iata)
            going_to = str(n_trip.route_2.route.going_from_iata)

            date_out = str(n_trip.route_1.date)
            date_return = str(n_trip.route_2.date)

            # Outbound link
            query_out = (
                f"Flights from "
                f"{n_trip.route_1.route.going_from_iata} "
                f"to {leaving_from} on {date_out} one way"
            )

            link_out = (
                "https://www.google.com/travel/flights?q="
                + quote(query_out)
            )

            # Return link
            query_return = (
                f"Flights from {going_to} "
                f"to {n_trip.route_2.route.going_to_iata} "
                f"on {date_return} one way"
            )

            link_return = (
                "https://www.google.com/travel/flights?q="
                + quote(query_return)
            )

            start_loc = n_trip.route_name_actual_1

            start_data = (
                airports_df[
                    airports_df["iata_code"] == start_loc
                ].latitude_deg.values[0],

                airports_df[
                    airports_df["iata_code"] == start_loc
                ].longitude_deg.values[0]
            )

            end_loc = n_trip.route_name_actual_2

            end_data = (
                airports_df[
                    airports_df["iata_code"] == end_loc
                ].latitude_deg.values[0],

                airports_df[
                    airports_df["iata_code"] == end_loc
                ].longitude_deg.values[0]
            )

            coords_map[start_data] = (
                airports_df[
                    airports_df["iata_code"] == start_loc
                ].name.values[0]
            )

            coords_map[end_data] = (
                airports_df[
                    airports_df["iata_code"] == end_loc
                ].name.values[0]
            )

            locations = city_coords.copy()
            # locations.append(start_data)
            # locations.append(end_data)
            print(locations)
            print(len(locations))
            route, distance = shortest_route(
                [start_data]+locations+[end_data],
                start_data,
                end_data
            )

            print("OPTIMISED ROUTE FOR TRIP")

            route_data = []

            for r in route:
                print(coords_map[r])

            for r in range(len(route) - 1):

                r1 = route[r]
                r2 = route[r + 1]

                travel_type = ""

                if distance[r] > 900:
                    travel_type = "plane"
                elif distance[r] > 50:
                    travel_type = "train"
                else:
                    travel_type = "taxi/car"

                route_data.append({
                    "from": (
                        coords_map[r1],
                        r1[0],
                        r1[1]
                    ),
                    "to": (
                        coords_map[r2],
                        r2[0],
                        r2[1]
                    ),
                    "type": travel_type
                })

            curr_map = build_map(route_data)

            print("____________________________________________________")
            print(".........")

            option_data = {
                "route_map": curr_map,

                "route_name_actual_1":
                    str(n_trip.route_name_actual_1),

                "route_name_actual_2":
                    str(n_trip.route_name_actual_2),

                "best_price":
                    float(n_trip.best_price),

                "route_1_date":
                    date_out,

                "route_2_date":
                    date_return,

                "route_1_going_from_iata":
                    leaving_from,

                "route_2_going_to_iata":
                    going_to,

                "route_1_distance_km":
                    float(n_trip.route_1.route.distance_km),

                "route_2_distance_km":
                    float(n_trip.route_2.route.distance_km),

                "link_outbound":
                    link_out,

                "link_return":
                    link_return
            }

            # =========================
            # DEDUPE LOGIC
            # =========================

            option_key = (
                option_data["route_name_actual_1"],
                option_data["route_name_actual_2"],
                option_data["route_1_date"],
                option_data["route_2_date"],
                option_data["route_1_going_from_iata"],
                option_data["route_2_going_to_iata"],
                option_data["best_price"]
            )

            if option_key not in grouped_routes[key]["seen_options"]:
                grouped_routes[key]["seen_options"].add(option_key)
                grouped_routes[key]["options"].append(option_data)

    # =========================
    # CLEANUP
    # =========================

    for route in grouped_routes.values():
        route.pop("seen_options", None)

    # Convert to list
    print("LISTING")

    results = list(grouped_routes.values())

    # Sort options inside each route
    print("FIXING!")

    for trip in results:
        trip["options"].sort(
            key=lambda x: x["best_price"]
        )

    # Remove empty routes
    print("DONE FIX")

    results = [
        trip for trip in results
        if trip["options"]
    ]

    print("START SORT")

    # Sort routes by cheapest option
    results.sort(
        key=lambda x: x["options"][0]["best_price"]
    )

    print("RENDER")

    # print(results)
    return render_template("flights.html", trips=results)

    # for trip in optimal_trips:
    #     optimised_n_trips = trip.get_n_best(3)

    #     trip_data = {
    #         "n_best_count": int(len(optimised_n_trips)),
    #         "departing_from": trip.screen1,
    #         "landing_in": trip.screen2,
    #         "options": []
    #     }

    #     for n_trip in optimised_n_trips:
    #         option_data = {
    #             "route_name_actual_1": str(n_trip.route_name_actual_1),
    #             "route_name_actual_2": str(n_trip.route_name_actual_2),
    #             "best_price": float(n_trip.best_price),

    #             "route_1_date": str(n_trip.route_1.date),
    #             "route_2_date": str(n_trip.route_2.date),

    #             "route_1_going_from_iata": str(n_trip.route_1.route.going_to_iata),
    #             "route_2_going_to_iata": str(n_trip.route_2.route.going_from_iata),

    #             "route_1_distance_km": float(n_trip.route_1.route.distance_km),
    #             "route_2_distance_km": float(n_trip.route_2.route.distance_km),
    #         }

    #         trip_data["options"].append(option_data)

    #     # sort options cheapest → expensive
    #     trip_data["options"].sort(key=lambda x: x["best_price"])

    #     results.append(trip_data)

    # # sort routes by cheapest option
    # # results.sort(key=lambda x: x["options"][0]["best_price"] if x["options"] else float("inf"))
    # results = [trip for trip in results if trip["options"]]
    # results.sort(key=lambda x: x["options"][0]["best_price"])
    # return render_template("flights.html", trips=results)
    # # for trip in optimal_trips:
    # #     optimised_n_trips=trip.get_n_best(3)
    # #     print("LEN",len(optimised_n_trips))
    # #     for n_trip in optimised_n_trips:
    # #         print(n_trip.route_name_actual_1)
    # #         print(n_trip.route_name_actual_2)
    # #         print(n_trip.best_price)
        
    # #         print(n_trip.route_1.date)
    # #         print(n_trip.route_2.date)
    # #         print(n_trip.route_1.route.going_to_iata)
    # #         print(n_trip.route_2.route.going_from_iata)  
    # #         print(n_trip.route_1.route.distance_km)
    # #         print(n_trip.route_2.route.distance_km)
    # #         # print(n_trip.route_1.route.desired_destination)
    # #         # print(n_trip.route_2.route.desired_destination)


    # #         print("_______________________________")
    # results = []
    # results=get_cheapest_n_flights(optimal_trips,3)
    # for trip in optimal_trips:
    #     optimised_n_trips = trip.get_n_best(3)

    #     trip_data = {
    #         "n_best_count": int(len(optimised_n_trips)),
    #         "departing_from":trip.screen1,
    #         "landing_in":trip.screen2,
    #         "options": []
    #     }

    #     for n_trip in optimised_n_trips:
    #         option_data = {
    #             "route_name_actual_1": str(n_trip.route_name_actual_1),
    #             "route_name_actual_2": str(n_trip.route_name_actual_2),
    #             "best_price": float(n_trip.best_price),

    #             "route_1_date": str(n_trip.route_1.date),
    #             "route_2_date": str(n_trip.route_2.date),

    #             "route_1_going_from_iata": str(n_trip.route_1.route.going_to_iata),
    #             "route_2_going_to_iata": str(n_trip.route_2.route.going_from_iata),

    #             "route_1_distance_km": float(n_trip.route_1.route.distance_km),
    #             "route_2_distance_km": float(n_trip.route_2.route.distance_km),
    #         }


    #         trip_data["options"].append(option_data)

    #     results.append(trip_data)

    # return jsonify({
    #     "status": "ok",
    #     "received": "done",
    #     "trips": make_json_safe(results)
    # })
        # pinrt("hi")
    # return jsonify({
    #     "status": "ok",
    #     "received": "done"
    # })

if __name__ == "__main__":
    app.run(debug=True)



