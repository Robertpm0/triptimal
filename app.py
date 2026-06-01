from flask import Flask, render_template, request, jsonify,redirect,url_for
import difflib
import numpy as np
# from math import radians, sin, cos, sqrt, atan2
import os
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
import uuid
import geopandas as gpd
'''
algorithm:
for each city in cities to go to
    find routes < desired window time from takeoff loc to cities to go to
    best_n_prices= get_best_prices(routes in window  )
    for each city in cities to go to
        find routes < desired window time from takeoff loc to cities to go to
 


'''
# amadeus = Client(
#     client_id="vFAnLBDXF7IGZI4TYSfau1WqikrAiLJ4",
#     client_secret="LH6NEq7YBdStt2hP"
# )
cities_df=pd.read_csv("worldcities.csv")
cities_df["screen_name"]=cities_df["city"]+"_"+cities_df["country"]+"_"+cities_df["admin_name"]
# print(cities_df.head())
ITEMS=cities_df['city_uid']=cities_df["city"]+"_"+cities_df["country"]+"_"+cities_df["id"].astype(str)+"_"+cities_df["admin_name"]
ITEMS=ITEMS.dropna()
ITEMS=ITEMS.values
app = Flask(__name__)
# trips_cache={}

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
        min_n=n_days[0]
        max_n=n_days[1]
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
                        # if (n_days-1)<=abs((route2.date-route.date).days)<=(n_days+1):
                        if min_n<=abs((route2.date-route.date).days)<=max_n:
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
# def cheapest_on_date(route, date):
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



def convert_k_price(k_price):
    price=k_price.split(".")

    thousands=int(price[0])*1000
    if len(price)==1:
        return thousands
    
    k_purge=price[1].replace("K","").replace("k","")
    hunnids=int(k_purge)
    price=thousands+hunnids
    return price


def get_driver():
    options = Options()
    # options.add_argument("--headless=new")  # modern headless mode
    # options.add_argument("--disable-gpu")
    # options.add_argument("--no-sandbox")
    # options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--ignore-certificate-errors")
    # options.add_argument("--incognito")
    # options.add_argument("--window-size=1920,1080")

    # driver = webdriver.Chrome(options=options)
    # driver=webdriver.Chrome(options=options,service=Service("C:\chromedriver-win64\chromedriver.exe"))
    auto_service=Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(options=options,service=auto_service)

    # driver=webdriver.Chrome(options=options)
    return driver


# driver = get_driver()
def get_flight_price(route,date,end_date,psgr,travel_class):
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
    # retries=0
    # while retries<3:
    # try:
    driver=get_driver()
        # break
#     except:
#         # retries+=1
# # if retries>3:
#         return all_routes

    # driver=get_driver()
#    driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20LAS%20to%20HEL%20on%20{date_str}%20one%20way")
    # print(leaving_from)
    # print(going_to)
    # print("leaf")
    # print("go")
    # driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20{leaving_from}%20to%20{going_to}%20on%20{date_str}%20one%20way")
    passengers = psgr
    adults=passengers[0]
    children=passengers[1]
    infants=passengers[2]
    # driver.get(
    #     f"https://www.google.com/travel/flights?q="
    #     f"{passengers}%20passengers%20Flights%20from%20"
    #     f"{leaving_from}%20to%20{going_to}%20on%20"
    #     f"{date_str}%20one%20way"
    # )

        # Convert your dropdown value into Google Flights wording
    flight_class_map = {
        "economy": "Economy",
        "premium_economy": "Premium Economy",
        "business": "Business Class",
        "first_class": "First Class"
    }

    flight_class_google = flight_class_map.get(travel_class, "Economy")

    # Build passenger text
    passenger_parts = []

    if adults > 0:
        passenger_parts.append(f"{adults} adults")

    if children > 0:
        passenger_parts.append(f"{children} children")

    if infants > 0:
        passenger_parts.append(f"{infants} infants")

    passenger_string = ", ".join(passenger_parts)

    # Complete Google Flights URL
    driver.get(
        f"https://www.google.com/travel/flights?q="
        f"{passenger_string}%20"
        f"{flight_class_google}%20Flights%20from%20"
        f"{leaving_from}%20to%20"
        f"{going_to}%20on%20"
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
    try:
        body_element = driver.find_element(By.TAG_NAME, "body")
    except:
        return all_routes
    all_page_text = body_element.text
    # print(all_page_text)
    # print("AFDASD", driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[2]/div[2]/div/div[2]/div[3]/ul/li[1]/div/div[2]/div/div[7]/div").text)
    try:
        if going_to not in all_page_text or leaving_from not in all_page_text:
            return all_routes
        driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[1]/div/div/div[1]/div/div[1]/div/input").click()
        time.sleep(2)
        cals=driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[2]/div[2]/div[2]/div[2]/div/div/div[1]/div")
        time.sleep(2)
        cals2=cals.find_elements(By.XPATH, '//*[@role="rowgroup"]')
    except:
        return all_routes
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
                print(calendar.split("\n"))
                try:
                    if "$" in calendar.split("\n")[calendar_idx]:
                        if "k" in calendar.split("\n")[calendar_idx].replace("$","").replace(",","").lower() or "K" in calendar.split("\n")[calendar_idx].replace("$","").replace(",",""):
                            price=convert_k_price(calendar.split("\n")[calendar_idx].replace("$","").replace(",",""))
                            curr_route=Dated_Routes(route,price,curr_date)
                        else:
                            curr_route=  Dated_Routes(route, float(calendar.split("\n")[calendar_idx].replace("$","").replace(",","")), curr_date)


                            # price=convert_k_price(calendar.split("\n")[calendar_idx].replace("$","").replace(",",""))

                            # curr_route=  Dated_Routes(route, price, curr_date)
                
                        all_routes.append(curr_route)
                except:
                    return all_routes
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


from datetime import date as dt_date

from fli.search import SearchDates
from fli.models import (
    Airport,
    DateSearchFilters,
    FlightSegment,
    PassengerInfo,
    SeatType,
    TripType,
)


def get_flight_price(route, date, end_date, psgr, travel_class):

    all_routes = []

    leaving_from = route.going_from_iata
    going_to = route.going_to_iata

    # Preserve your cache behavior exactly
    for route2 in all_flights:
        if route2.to == going_to and route2.frm == leaving_from:
            return route2.route

    adults = psgr[0]
    children = psgr[1]
    infants = psgr[2]

    seat_type_map = {
        "economy": SeatType.ECONOMY,
        "premium_economy": SeatType.PREMIUM_ECONOMY,
        "business": SeatType.BUSINESS,
        "first_class": SeatType.FIRST,
    }

    try:

        filters = DateSearchFilters(
            trip_type=TripType.ONE_WAY,
            passenger_info=PassengerInfo(
                adults=adults,
                children=children,
                infants_in_seat=0,
                infants_on_lap=infants,
            ),
            flight_segments=[
                FlightSegment(
                    departure_airport=[[Airport[leaving_from], 0]],
                    arrival_airport=[[Airport[going_to], 0]],
                    travel_date=date.isoformat(),
                )
            ],
            from_date=date.isoformat(),
            to_date=end_date.isoformat(),
            seat_type=seat_type_map.get(
                travel_class,
                SeatType.ECONOMY,
            ),
        )

        search = SearchDates()

        results = search.search(filters)

        # results are DatePrice objects
        for result in results:

            try:
                curr_date = result.date

                # Some versions return tuple/list of dates
                if isinstance(curr_date, (list, tuple)):
                    curr_date = curr_date[0]

                price = float(result.price)

                curr_route = Dated_Routes(
                    route,
                    price,
                    curr_date,
                )

                all_routes.append(curr_route)

            except Exception:
                continue

        temp = All_Routes(
            going_to,
            leaving_from,
            all_routes,
        )

        all_flights.append(temp)

        return all_routes

    except Exception as e:
        print(e)
        return all_routes

def cheapest_each_date_parallel(routes, dates,psgr,travel_class, max_workers=12):
    results = []
    sd=[]
    ed=[]
    # print("DATES!!!: ",dates)
    for date in dates:
        sd.append(date[0])
        ed.append(date[-1])
    psgrs=[psgr]*len(dates)
    travel_class=[travel_class]*len(dates)
    print("NUMBER OF LINKS TO SCRAPE: ",len(psgrs))
    results2=[]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(get_flight_price, routes, sd,ed,psgrs,travel_class):
                # result=[x for x in result if x is not None]

                results.extend(result)
                results2.append(result)
    print("LEN REYSKTS",len(results2))
    return results,results2
# import asyncio
# from datetime import timedelta
# from playwright.async_api import async_playwright

# # GLOBAL CACHE
# all_flights = []

# # Tune carefully for Google
# MAX_CONCURRENT_PAGES = 4

# SEM = asyncio.Semaphore(MAX_CONCURRENT_PAGES)


# async def block_assets(route):
#     """
#     Block unnecessary resources for huge speed gains
#     """
#     if route.request.resource_type in [
#         "image",
#         "media",
#         "font",
#         "stylesheet",
#     ]:
#         await route.abort()
#     else:
#         await route.continue_()


# async def scrape_google_flights(
#     browser,
#     route,
#     start_date,
#     end_date,
#     psgr
# ):

#     async with SEM:

#         leaving_from = route.going_from_iata
#         going_to = route.going_to_iata

#         # CACHE HIT
#         for existing in all_flights:
#             if (
#                 existing.to == going_to
#                 and existing.frm == leaving_from
#             ):
#                 return existing.route

#         page = await browser.new_page()

#         try:

#             # SPEED OPTIMIZATION
#             await page.route("**/*", block_assets)

#             url = (
#                 "https://www.google.com/travel/flights?q="
#                 f"{psgr}%20passengers%20Flights%20from%20"
#                 f"{leaving_from}%20to%20{going_to}%20on%20"
#                 f"{start_date.isoformat()}%20one%20way"
#             )

#             print(f"SCRAPING: {leaving_from} -> {going_to}")

#             await page.goto(
#                 url,
#                 wait_until="domcontentloaded",
#                 timeout=45000
#             )

#             # Wait for flight page content
#             await page.wait_for_selector("body", timeout=15000)

#             body_text = await page.locator("body").inner_text()

#             # Validate page loaded correctly
#             if (
#                 leaving_from not in body_text
#                 or going_to not in body_text
#             ):
#                 await page.close()
#                 return []

#             #
#             # CLICK DATE INPUT
#             #
#             try:

#                 date_input = page.locator(
#                     'input[placeholder*="Departure"]'
#                 ).first

#                 await date_input.click(timeout=5000)

#             except:
#                 print("Could not open calendar")
#                 await page.close()
#                 return []

#             #
#             # WAIT FOR CALENDAR
#             #
#             await page.wait_for_selector(
#                 '[role="rowgroup"]',
#                 timeout=10000
#             )

#             calendars = await page.locator(
#                 '[role="rowgroup"]'
#             ).all()

#             curr_date = start_date 

#             all_routes = []

#             for cal in calendars:

#                 text = await cal.inner_text()

#                 lines = text.split("\n")

#                 idx = 0

#                 while idx < len(lines):

#                     line = lines[idx]

#                     try:
#                         day_num = int(line)

#                         if idx + 1 < len(lines):

#                             price_line = lines[idx + 1]

#                             if "$" in price_line:

#                                 price = float(
#                                     price_line
#                                     .replace("$", "")
#                                     .replace(",", "")
#                                 )

#                                 curr_route = Dated_Routes(
#                                     route,
#                                     price,
#                                     curr_date
#                                 )

#                                 all_routes.append(curr_route)

#                                 curr_date += timedelta(days=1)

#                                 if curr_date > end_date:

#                                     temp = All_Routes(
#                                         going_to,
#                                         leaving_from,
#                                         all_routes
#                                     )

#                                     all_flights.append(temp)

#                                     await page.close()

#                                     return all_routes

#                     except:
#                         pass

#                     idx += 1

#             await page.close()

#             return all_routes

#         except Exception as e:

#             print("SCRAPE ERROR:", e)

#             await page.close()

#             return []


# async def cheapest_each_date_parallel(
#     routes,
#     dates,
#     psgr
# ):

#     results = []

#     async with async_playwright() as p:

#         #
#         # SINGLE SHARED BROWSER
#         #
#         browser = await p.chromium.launch(

#             headless=True,

#             args=[
#                 "--disable-blink-features=AutomationControlled",
#                 "--disable-dev-shm-usage",
#                 "--no-sandbox",
#                 "--disable-gpu",
#             ]
#         )

#         tasks = []

#         for i, route in enumerate(routes):

#             start_date = dates[i][0]
#             end_date = dates[i][-1]

#             tasks.append(

#                 scrape_google_flights(
#                     browser,
#                     route,
#                     start_date,
#                     end_date,
#                     psgr
#                 )
#             )

#         #
#         # TRUE ASYNC CONCURRENCY
#         #
#         all_results = await asyncio.gather(*tasks)

#         for r in all_results:
#             results.extend(r)

#         await browser.close()

#     return results
    # return sorted(results, key=lambda x: x["date"])4

def get_flight_prices(frm,to,dates,n_best,is_going_to,max_distance_away,psgr,travel_class,dists):

    # get the routes
    # check if we are going to our vacation
    if is_going_to==True:
        going_to_routes=[]
        # base_flight=Unpriced_Routes(frm,to,0,0,0,to)
        # going_to_routes.append(base_flight)
        for t,d in zip(to,dists):
            base_flight=Unpriced_Routes(frm,t,d,0,0,t)
            going_to_routes.append(base_flight)
    else:
        going_to_routes=[]
        # base_flight=Unpriced_Routes(frm,to,0,0,0,frm)
        # going_to_routes.append(base_flight)
        for f,d in zip(frm,dists):
            base_flight=Unpriced_Routes(f,to,d,0,0,f)
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

    results,results2=cheapest_each_date_parallel(going_to_routes,all_dates,psgr,travel_class)
    # print(len(results2))
    # for date in dates:

    # import asyncio

    # results = asyncio.run(
    # cheapest_each_date_parallel(
    #     going_to_routes,
    #     all_dates,
    #     psgr=psgr
    #     ,travel_class=travel_class
    # )
    #     )
        # print("LEN ROUTE",len(going_to_routes))
        # for route in going_to_routes:
        #     print("r")
        #     r = cheapest_on_date(route.going_from_iata, route.going_to_iata, date)
        #     if r:
        #         print("got")
        #         temp_dated_trip=Dated_Routes(route,r["price"],date)
        #         results.append(temp_dated_trip)
    # print(len(results))
    # print("done")
    # results=[x for x in results if x is not None else ]
    # results2=[x for x in results2 if x is not None]

    # print(len(results))
    return results,results2 
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


    d_new_airports1=[]
    d_new_airports2=[]
    d_new_airports3=[]
    d_new_airports4=[]
    d_new_airports5=[]
    
    dist=dists.nsmallest(n)
    for a,d in zip(airports,dist):
        if gdf[gdf["iata_code"]==a]["type"].values[0]=="international_airport":
            new_airports1.append(a)
            d_new_airports1.append(d)
            
        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="large_airport":
            new_airports2.append(a)
            d_new_airports2.append(d)
            
        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="medium_airport":
            new_airports3.append(a)
            d_new_airports3.append(d)

        elif gdf[gdf["iata_code"]==a]["type"].values[0]=="small_airport":
            new_airports4.append(a)
            d_new_airports4.append(d)

        else:
            new_airports5.append(a)
            d_new_airports5.append(d)

    new_airports=new_airports1+new_airports2+new_airports3+new_airports4+new_airports5
    d_new_airports=d_new_airports1+d_new_airports2+d_new_airports3+d_new_airports4+d_new_airports5

    return new_airports[:n],d_new_airports[:n]

def optimal_find_trips(cities,keys,start_date,end_date,num_days,origin,passgr,tc,opt,optional_iata=None):
    # print("origin",origin)
    # print(len(cities_df))
    df = pd.read_csv("airports.csv")
    df=df[~df["iata_code"].isnull()]
    # df=df[df["icao_code"].isnull()]

    gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df.longitude_deg, df.latitude_deg),
    crs="EPSG:4326"   # WGS84 lat/lon
    )
    if opt==False:
        origin_data=cities_df[cities_df["id"]==int(origin)]
        # print(origin_data.head())

    #     target_lat = origin_data.lat.values[0]
    #     target_lon = origin_data.lng.values[0]
    #     target_point = gpd.GeoSeries([Point(target_lon, target_lat)], crs="EPSG:4326")

    #     gdf_m = gdf.to_crs(gdf.estimate_utm_crs())
    #     target_m = target_point.to_crs(gdf_m.crs).iloc[0]

    # # find closest row
    #     closest_idx = gdf_m.distance(target_m).idxmin()
    #     closest_row = gdf.loc[closest_idx]

        origin_iata,dist=find_nearest_airports(origin_data.lat.values[0],origin_data.lng.values[0],gdf,n=3)
    else:
        origin_iata=[optional_iata]
        dist=[0]


    min_days=num_days[0]
    max_days=num_days[1]
    start_date = datetime.strptime(start_date,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date,"%Y-%m-%d").date()
    retries=0
    while retries <3:
        # print("ORIGIN",origin_iata)
        for cty in origin_iata:
            all_flights=[]
            starting_city=cty# iata code
            to_cost=0

            # max_arrival_date=end_date-timedelta(days=num_days)
            max_arrival_date=end_date-timedelta(days=min_days)
            #iata code
            to_trips=[]
            from_trips=[]
            city_iata=[]
            actual_names=[]
            to_names=[]
            from_names=[]
            delta_dists=[]
            for key in keys:
                origin_data=cities_df[cities_df["id"]==int(key)]  
                curr_iata,dist=find_nearest_airports(origin_data.lat.values[0],origin_data.lng.values[0],gdf,n=4)
                city_iata.extend(curr_iata)
                actual_names.extend([origin_data.screen_name.values[0]]*len(curr_iata))
                delta_dists.extend(dist)
            min_n_flights2,min2=get_flight_prices(starting_city,city_iata,[start_date,max_arrival_date],6,True,400,passgr,tc,delta_dists)
            ctr=0
            # print("LEN_MIN2_0",len(min2))

            # print(len(min2))
            # print(len(city_iata))
            for arriv_city,actual_name in zip(city_iata,actual_names):
                # print(arriv_city)
                # print("start")
                # print(actual_name)
                # min_n_flights=get_flight_prices(starting_city,arriv_city,[start_date,max_arrival_date],6,True,400,passgr,tc)

                # print("NUM FLIGHTS",len(min_n_flights))
                # print("CITY: ",actual_name)
                min_n_flights=min2[ctr]
                min_n_flights=[x for x in min_n_flights if x is not None]
                curr_trip= Flight_Possibilites(to=arriv_city,frm=starting_city) 
                for flight in min_n_flights:
                    curr_trip.add_route(flight)
                # iata code
                to_trips.append(curr_trip)
                to_names.append(actual_name)
                ctr+=1

            print("STARTING FLIGHT HOME SEARCH")
            min_depart_date=start_date+timedelta(days=min_days)

            min_flights_depart2,min22=get_flight_prices(city_iata,starting_city,[min_depart_date,end_date],6,False,400,passgr,tc,delta_dists)
            ctr=0
            # print("LEN_MIN2",len(min22))
            for depart_city,actual_name in zip(city_iata,actual_names):
                # print("start back")
                # print(actual_name)
                # min_flights_depart=get_flight_prices(depart_city,starting_city,[min_depart_date,end_date],6,False,400,passgr,tc)
                # print("NUM FLIGHTS",len(min_flights_depart))
                min_flights_depart=min22[ctr]
                min_flights_depart=[x for x in min_flights_depart if x is not None]
                curr_trip=Flight_Possibilites(to=starting_city,frm=depart_city)
                # print("TO",start)
                for flight in min_flights_depart:
                    curr_trip.add_route(flight)
                from_trips.append(curr_trip)
                from_names.append(actual_name)
                ctr+=1
            # print(len(to_trips))
            # print("LLLL")
            # print(len(from_trips))
            optimizer=Flight_Optimizer(to_flights=to_trips,from_flights=from_trips,t_names=to_names,frm_names=from_names)
            optimised_routes=optimizer.optimise(3,num_days)
            # print("LENOPT",len(optimised_routes))
            if len(optimised_routes)!=0:
                # print("OPTIMISED ROUTES")
                retries=4
                return optimised_routes

                # break
        retries+=1
    return optimised_routes





# Example dataset


# ITEMS={}
@app.route("/")
def index():
    user=session.get("user")
    return render_template("index.html",user=user)


from flask import request, jsonify


@app.route("/save_trip", methods=["POST"])
def save_trip():
    # global trips_data
    # trips_data=trips_cache[session.get("trip_id")]
    trips_data=get_last_trip()
    data = request.get_json()

    trip_id = data.get("trip_id")

    print("Saving trip:", trip_id)
    trips=session.get("trip_results")
    trips=trips_data
    user_id=session.get("user_id")
    # print("USER_ID",user_id)
    supabase=get_supabase()
    # supabase2 = create_client(
    # SUPABASE_URL,
    # SUPABASE_KEY
    # )
    # print("ACCES:",print(session.get("access_token")))
    # supabase.auth.refresh_session()

    try:
        supabase.postgrest.auth(session["access_token"])
    except:
        return jsonify({
        "success": False,
        "trip_id": trip_id
    })

    for trip in trips:
        # print("here
        # ")
        departing=trip["departing_from"]
        landing=trip["landing_in"]
        for t in trip["options"]:
            if t["trip_local_id"]==int(trip_id):
                print("INSERTING")
                # trip_2_save=trip["options"][0]
                trip_2_save=t
                result = (
                    supabase
                    .table("user_trips")
                    .insert({
                        "user_id": user_id,
                        "trip_info": trip_2_save,
                        "trip_key":[departing,landing]
                    })
                    .execute()
                )
    # Your future save logic goes here
    # Examples:
    # database.save_trip(user_id,current_trip)
    # saved_trips.append(trip_id)

    return jsonify({
        "success": True,
        "trip_id": trip_id
    })

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

AVIASALES_MARKER = "719019"


def format_aviasales_date(date_str):
    """
    Converts:
    YYYY-MM-DD -> DDMM

    Example:
    2026-09-14 -> 1409
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d%m")


# def generate_one_way_aviasales_link(
#     origin,
#     destination,
#     depart_date,
#     marker=AVIASALES_MARKER
# ):
#     """
#     Generates ONE WAY Aviasales link

#     Format:
#     /search/JFK1409CDG1
#     """

#     depart = format_aviasales_date(depart_date)

#     return (
#         f"https://www.aviasales.com/search/"
#         f"{origin}{depart}{destination}1"
#         f"?marker={marker}"
#     ) 


def generate_one_way_aviasales_link(
    origin,
    destination,
    depart_date,
    adults,
    children,
    infants,
    travel_class,
    marker=AVIASALES_MARKER
):
    """
    Generates ONE WAY Aviasales affiliate link

    UI travel_class values:
    - economy
    - premium_economy
    - business
    - first_class
    """

    depart = depart_date#format_aviasales_date(depart_date)

    # Convert UI value -> Aviasales value
    # AVIASALES_FLIGHT_CLASS_MAP = {
    #     "economy": "economy",
    #     "premium_economy": "comfort",
    #     "business": "business",
    #     "first_class": "first"
    # }
    AVIASALES_FLIGHT_CLASS_MAP = {
        "economy": 0,
        "premium_economy":0,
        "business": 1,
        "first_class": 1
    }

    trip_class = AVIASALES_FLIGHT_CLASS_MAP.get(
        travel_class,
        0
    )

    return (
        f"https://www.aviasales.com/search/"
        f"?origin_iata={origin}"
        f"&destination_iata={destination}"
        f"&depart_date={depart}"
        f"&adults={adults}"
        f"&children={children}"
        f"&infants={infants}"
        f"&trip_class={trip_class}"
        f"&marker={marker}"
    )
def delete_last_trip() -> bool:
    """
    Delete a trip from the last_trips table.

    Args:
        trip_id: The trip ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    trip_id=session.get("trip_id")
    try:
        supabase=get_supabase()
    except:

        supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )  
    (
        supabase.table("last_trips")
        .delete()
        .eq("trip_id", trip_id)
        .execute()
    )



def save_last_trip(trips):

    trip_id=session.get("trip_id")
    try:
        supabase=get_supabase()
    except:

        supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )  
    response = (
        supabase.table("last_trips")
        .upsert(
            {
                "trip_id": trip_id,
                "trip_data": trips
            }
        )
        .execute()
    )


# def save_trip(trip_id: str, trip_data: list) -> dict:
#     """
#     Save a trip to Supabase.

#     Args:
#         trip_id: Unique trip identifier
#         trip_data: List of dictionaries

#     Returns:
#         Saved row
#     """

#     response = (
#         supabase.table("last_trips")
#         .upsert(
#             {
#                 "trip_id": trip_id,
#                 "trip_data": trip_data
#             }
#         )
#         .execute()
#     )

#     return response.data[0]
@app.route("/submit", methods=["POST"])
def submit():
    print("START",dt.datetime.now())
    print("TOK",session.get("access_token"))
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    min_nights = request.form.get("min_nights")
    max_nights=request.form.get("max_nights")
    cities = request.form.getlist("cities")
    city_ids = request.form.getlist("city_ids")
    trav_class=request.form.get("travel_class")

    # remove empty entries (unselected inputs)
    cities = [c for c in cities if c]
    city_ids = [c for c in city_ids if c]
    
    origin_city = request.form.get("origin_city")
    origin_city_id = request.form.get("origin_city_id")
    optional_iata=request.form.get("origin_airport_code")
    optional=False
    if optional_iata is not None:
        optional=True
    # passengers=request.form.get("passengers")
    adults=int(request.form.get("adults"))
    children=int(request.form.get("children"))
    infants=int(request.form.get("infants"))
    passengers=[adults,children,infants]

    # Example: build trip request object
    trip = {
        "start_date": start_date,
        "end_date": end_date,
        "min_nights": int(min_nights),
        "max_nights": int(max_nights),
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
    optimal_trips=optimal_find_trips(cities,city_ids,start_date,end_date,[int(min_nights),int(max_nights)],origin_city_id,passengers,trav_class,optional,optional_iata)
    # print(len(optimal_trips))
    print("NUM_FOUND",len(optimal_trips))
    # print("START")
    # results=[]
    airports_df=pd.read_csv("airports.csv")
    grouped_routes = {}
    curr_id=0

    for trip in optimal_trips:
        # print("loop")

        key = (trip.screen1, trip.screen2)

        if key not in grouped_routes:
            grouped_routes[key] = {
                "departing_from": trip.screen2,
                "landing_in": trip.screen1,
                "options": [],
                "seen_options": set()  # used for deduping
            }

        # print("optimal")

        optimised_n_trips = trip.get_n_best(3)

        # print("LEN: ", len(optimised_n_trips))

        maps = []

        for n_trip in optimised_n_trips:
            outbound_origin = str(
                n_trip.route_1.route.going_from_iata
            )

            outbound_destination = str(
                n_trip.route_1.route.going_to_iata
            )

            outbound_date = str(
                n_trip.route_1.date
            )

            # ==========================================
            # RETURN FLIGHT
            # ==========================================

            return_origin = str(
                n_trip.route_2.route.going_from_iata
            )

            return_destination = str(
                n_trip.route_2.route.going_to_iata
            )

            return_date = str(
                n_trip.route_2.date
            )

            leaving_from = str(n_trip.route_1.route.going_to_iata)
            going_to = str(n_trip.route_2.route.going_from_iata)

            date_out = str(n_trip.route_1.date)
            date_return = str(n_trip.route_2.date)
            outbound_aviasales_link = (
                generate_one_way_aviasales_link(
                    origin=outbound_origin,
                    destination=outbound_destination,
                    depart_date=outbound_date,
                    marker=AVIASALES_MARKER,
                    adults=int(passengers[0]),
                    children=int(passengers[1]),
                    infants=int(passengers[2]),
                    travel_class=trav_class
                )
            )

            return_aviasales_link = (
                generate_one_way_aviasales_link(
                    origin=return_origin,
                    destination=return_destination,
                    depart_date=return_date,
                    marker=AVIASALES_MARKER,
                    adults=int(passengers[0]),
                    children=int(passengers[1]),
                    infants=int(passengers[2]),
                    travel_class=trav_class
                )
            )
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
            # print(locations)
            # print(len(locations))
            route, distance = shortest_route(
                [start_data]+locations+[end_data],
                start_data,
                end_data
            )

            # print("OPTIMISED ROUTE FOR TRIP")

            route_data = []

            # for r in route:
            #     # print(coords_map[r])

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

            # print("____________________________________________________")
            # print(".........")

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
                    int(float(n_trip.route_1.route.distance_km)/1000) if float(n_trip.route_1.route.distance_km)/1000 >20 else 0,# str(n_trip.route_name_actual_2).lower()!=going_to.lower() else 0,

                "route_2_distance_km":
                    # float(n_trip.route_2.route.distance_km)/1000,
                    int(float(n_trip.route_2.route.distance_km)/1000)if float(n_trip.route_2.route.distance_km)/1000 >20 else 0,# if str(n_trip.route_name_actual_1).lower()!=leaving_from.lower() else 0,

                "link_outbound":
                    #link_out,
                    outbound_aviasales_link,

                "total_dist":int(sum(distance)),

                "link_return":
                   # link_return
                   return_aviasales_link,
                   "trip_local_id":curr_id
                   
            }
            curr_id+=1

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
    # print("LISTING")

    results = list(grouped_routes.values())

    # Sort options inside each route
    # print("FIXING!")

    for trip in results:
        trip["options"].sort(

            key=lambda x: x["best_price"]
        )

    # Remove empty routes
    # print("DONE FIX")

    results = [
        trip for trip in results
        if trip["options"]
    ]

    # print("START SORT")

    # Sort routes by cheapest option
    results.sort(
        key=lambda x: x["options"][0]["best_price"]
    )

    # print("RENDER")

    # for trip in results:
    #     print("__________________________________________________")
    #     print(trip["options"][0])
    # session["trip_results"]=results
    # global trips_data
    trip_id = str(uuid.uuid4())

    # trips_cache[trip_id] = results
    # trips_data=results
    # delete last trip this session saved if regenerating results
    # to try and optimise table size
    if session.get("trip_id") is not None:
        delete_last_trip()
    session["trip_id"]=trip_id
    # print(len(results))
    save_last_trip(results)
    # user=session.get("user")
    print("END",dt.datetime.now())

    return redirect(url_for("flights"))

def get_last_trip() -> list | None:
    """
    Returns only the stored JSON trip_data.
    """
    trip_id=session.get("trip_id")
    try:
        supabase=get_supabase()
    except:

        supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )  
    response = (
        supabase.table("last_trips")
        .select("trip_data")
        .eq("trip_id", trip_id)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]["trip_data"]
@app.route("/flights")
def flights():
    # global trips_data
    # try:

        # td=trips_cache[session.get("trip_id")]
    td=get_last_trip()
    # except:
        # td=[]
# print(len(results))
    user=session.get("user")
    return render_template("flights.html", trips=td,user=user)

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



from flask import Flask, render_template, request, jsonify, session
from supabase import create_client

# app = Flask(__name__)
app.secret_key = "your-secret-key"

# def get_supabase():

#     if not access_token:
#         raise Exception("User not authenticated")

#     client = create_client(
#         SUPABASE_URL,
#         SUPABASE_KEY
#     )

#     client.postgrest.auth(access_token)

#     return client

def get_supabase():

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )

    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")

    if not access_token or not refresh_token:
        raise Exception("User not authenticated")

    try:
        # Rebuild Supabase auth session
        auth_response = client.auth.set_session(
            access_token,
            refresh_token
        )

        # Save refreshed tokens if Supabase rotated them
        session["access_token"] = auth_response.session.access_token
        session["refresh_token"] = auth_response.session.refresh_token

    except Exception:
        session.clear()
        raise Exception("Login expired")

    client.postgrest.auth(session["access_token"])

    return client
# @app.route("/")
# def home():
#     user = session.get("user")
#     return render_template(
#         "index.html",
#         user=user
#     )


@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    # print("HI")
    # supabase=get_supabase()
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    # print(SUPABASE_URL)
    access_token = session.get("access_token")

    # if not access_token:
    #     raise Exception("User not authenticated")

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )
    # print(data)
    try:
        supabase.auth.sign_up({
            "email": data["email"],
            "password": data["password"]
        })

        return jsonify({
            "success": True,
            "message": "Account created"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })


@app.route("/login", methods=["POST"])
def login():

    data = request.json

    SUPABASE_URL = os.getenv("SUPABASE_URL")#"https://YOUR_PROJECT.supabase.co"
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    # print(SUPABASE_URL)
    # access_token = session.get("access_token")

    # if not access_token:
    #     raise Exception("User not authenticated")

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

    try:

        result = supabase.auth.sign_in_with_password({
            "email": data["email"],
            "password": data["password"]
        })
        session["access_token"]=result.session.access_token
        session["refresh_token"] = result.session.refresh_token
        session["user"] = result.user.email
        session["user_id"]=result.user.id
        return jsonify({
            "success": True,
            "user": result.user.email
        })

    except Exception as e:
        if "invalid" in str(e):
            e="Invalid log in credentials. Please enter credentials and press sign up or re check and retry your login credentials"
        return jsonify({
            "success": False,
            "message": str(e)
        })


@app.route("/logout", methods=["GET","POST"])
def logout():

    session.clear()
    session.modified = True

    return jsonify({
        "success": True,
        "user": None
    })
# = "__main__":
#     app.run(debug=True)
 

@app.route("/open_saved_flights")
def open_saved_flights():
    supabase=get_supabase()
    user_id=session.get("user_id")
    try:
        supabase.postgrest.auth(session["access_token"])
    except:
        return jsonify({
        "success": False
        # "trip_id": trip_id
    })

    result = (
    supabase
    .table("user_trips")
    .select("*")
    .eq("user_id", user_id)
    .order("added_on", desc=True)
    .execute()
    )

    trips = result.data
    results={}
    for trip in trips:
        try:
            departing=trip["trip_key"][0]
            landing=trip["trip_key"][1]
        except:
            departing="legacy_trip"
            landing="legacy_trip_"
        trip_key=(departing,landing)

        if trip_key not in results:
            results[trip_key]={
                "departing_from":departing,
                "landing_in":landing,
                "options":[]
            }
        results[trip_key]["options"].append(trip["trip_info"])

        # if key not in grouped_routes:
        #     grouped_routes[key] = {
        #         "departing_from": trip.screen2,
        #         "landing_in": trip.screen1,
        #         "options": [],
        #         "seen_options": set()  # used for deduping
        #     }
    results = list(results.values())

    # Any backend logic here if needed



    today = dt.date.today()

    upcoming_trips = []
    past_trips = []

    for trip in results:

        start_dates = []

        for opt in trip["options"]:
            try:
                start_dates.append(
                    datetime.strptime(
                        opt["route_1_date"],
                        "%Y-%m-%d"
                    ).date()
                )
            except:
                pass

        if not start_dates:
            upcoming_trips.append(trip)
            continue

        trip_start = min(start_dates)

        if trip_start >= today:
            upcoming_trips.append(trip)
        else:
            past_trips.append(trip)

    return render_template(
        "saved_flights.html",
        trips=results,
        upcoming_trips=upcoming_trips,
        past_trips=past_trips
    )

    # return render_template(
    #     "saved_flight s.html",
    #     trips=results
    # )


if __name__ == "__main__":
    app.run()