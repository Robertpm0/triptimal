from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from datetime import date as dt_date
from datetime import datetime,timedelta
driver= webdriver.Chrome(service=Service("C:\chromedriver-win64\chromedriver.exe"))
# driver.get("https://www.bing.com/travel/flight-search?q=flights+from+las-hel&src=las&des=hel&ddate=2026-03-09&isr=0&rdate=2026-03-11&cls=0&adult=1&child=0&infant=0&form=FLAFLI&entrypoint=L1FHUB")

# time.sleep(10)
# flight_cont=driver.find_element(By.CLASS_NAME,"itineraryCardContainer")
# flights=flight_cont.find_elements(By.TAG_NAME,"div")
# print("NUM FLIGHTS",len(flights))
# for fl in flights:
#     print(fl.text)
#     print("_____________")
def diff_month(newest_date, oldest_date):
    return (newest_date.year - oldest_date.year) * 12 + newest_date.month - oldest_date.month

def get_flight_price(route,date,end_date):    
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
    try:
    # Ensure Duffel ISO date string
        if isinstance(date, dt_date):
            date_str = date.isoformat()
        else:
            date_str = str(date)
    except:
        pass
    leaving_from=route.going_from_iata
    going_to=route.going_to_iata
# driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20JFK%20to%20LAX%20on%202026-03-15%20one%20way")
    driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20{leaving_from}%20to%20{going_to}%20on%20{date_str}%20one%20way")
    start_month=date.month
    end_month=end_date.month
    if date.year!=end_date.year:
        end_year=end_date.year
    else:
        end_year=date.year
    time.sleep(5)
    # click calendar
    driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[1]/div/div/div[1]/div/div[1]/div/input").click()
    time.sleep(8)
    cals=driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[2]/div[2]/div[2]/div[2]/div/div/div[1]/div")
    time.sleep(3)
    cals2=cals.find_elements(By.XPATH, '//*[@role="rowgroup"]')
    num_months=diff_month(end_date,date)
    curr_month =range(start_month,start_month+num_months+2)
    mo_idx=0
    num_days=abs((date-end_date).days)
    start=False
    curr_date=date
    all_routes=[]
    for mo in curr_month:
        calendar=cals2[mo_idx].text
        calendar_idx=1
        for day in calendar.split("\n"):
            if day ==calendar.split("\n")[-1]:
                break
            if day ==date.day and mo_idx==0:
                start=True
            if start==True:
                if "$" in calendar.split("\n")[calendar_idx]:
                    curr_route=  Dated_Routes(route, float(calendar.split("\n")[calendar_idx].replace("$","")), curr_date)
                    all_routes.append(curr_route)
                
            curr_date=curr_date+timedelta(days=1)
            calendar_idx+=1

            if curr_date==end_date:
                return all_routes
        mo_idx+=1

driver.get(f"https://www.google.com/travel/flights?q=Flights%20from%20JFK%20to%20LAX%20on%202026-03-15%20one%20way")

time.sleep(6)
driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[1]/div/div/div[1]/div/div[1]/div/input").click()
time.sleep(8)
cals=driver.find_element(By.XPATH,"/html/body/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div/div[2]/div[2]/div/div/div[2]/div[2]/div[2]/div[2]/div/div/div[1]/div")
time.sleep(3)
cals2=cals.find_elements(By.XPATH, '//*[@role="rowgroup"]')
for cal in cals2[:2]:
    print(cal.text.split('\n'))
    # print(cal.text)
    print("____________________ ")