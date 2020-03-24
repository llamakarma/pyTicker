#!/usr/bin/env python3.6

# Requires Python 3.6

# Package information

version = "20200324-03"
newthisrelease = """New features this release:
- USD support (i.e. 1:1 exchange rate, hide currency conversion)
- Replace mandatory parameters with defaults, provide easy access variables to adjust
- Code tidy up/comments
- Revised some outputs
- Handle Yahoo API exceptions better (thanks Flacko)"""

# Cmdline parameter defaults

defcurrency = "usd"
defsymbol = "^gspc"
defmulti = 1
defthresh = 0
defrefresh = 20

if (defthresh == 0):
    threshstatus = "disabled"
else:
    threshstatus = defthresh


# Libraries

import signal
import sys
import requests
import requests_html
import time
import argparse
import string

from datetime import datetime
from pytz import timezone
from yahoo_fin import stock_info as si

# Handle puke

def signal_handler(sig, frame):
    print()
    print()
    print('Thanks for all the fish, smeg head.')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Get command line parameters

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description = "pyTicker version " + version,
    epilog = newthisrelease)
parser.add_argument("-i", type=int, help="refresh interval in seconds (default " + str(threshstatus) + ")")
parser.add_argument("-m", type=int, help="multiplier (Price x Multiplier = Value) (default " + str(defmulti) + ")")
parser.add_argument("-t", type=int, help="threshold value for alerts (default disabled)")
parser.add_argument("-s", type=str, help="stock symbol to watch (default " + defsymbol.upper() + ")")
parser.add_argument("-c", choices=["eur", "gbp", "usd", "zar"], type=str, help="select threshold/value currency (default " + defcurrency.upper() + ")")

args = parser.parse_args()

# Setup basic variables

if (args.c == None):
    currency = defcurrency
else:
    currency = args.c

if currency == "gbp":
   csymb = "£"
elif currency == "eur":
    csymb = "€"
elif currency == "zar":
    csymb = "R"
elif currency == "usd":
    csymb = "$"
else:
    csymb = "#"

if (args.s == None):
    symbol = defsymbol
else:
    symbol = args.s
if (args.m == None):
    multiplier = defmulti
else:
    multiplier = args.m
if (args.t == None):
    threshold = defthresh
else:
    threshold = args.t
bestvalue = 0
if (args.i == None):
    refresh = defrefresh
else:
    refresh = args.i
vdelta = ""
pdelta = ""
fdelta = ""
bestprice = 0
lowfx = 0

# Flags for conditional formatting

firstrun = True
ticktock = True

# Collect start of first run

startdate = datetime.now()
startdate = startdate.strftime("%d-%m-%Y")
starttime = datetime.now()
starttime = starttime.strftime("%H:%M:%S")
starttimeEST = datetime.now(timezone('America/New_York'))
starttimeEST = starttimeEST.strftime("%H:%M:%S")

# Set column widths

col1 = 15
if (len(str(threshold)) < 10):
    col2 = 15
else:
    col2 = len(str(threshold)) + 5
col3 = 18
col4a = 10
col4b = col4a + col3
maxwidth = col1 + col2 + col3 + col4a

# Generate delimiter line between iterations based on output width

delimiter = "\r"
for i in range(maxwidth):
    delimiter = delimiter + "-"

# Go!

print()
print(delimiter)
print()
print(str.ljust("Version:", col1) + str.ljust(version, col2))
print(str.ljust("Stock:", col1) + str.ljust(symbol.upper(), col2) + str.ljust("Currency:", col3) + str.rjust("(" + csymb + ") " + currency.upper(), col4a))
if (threshold == 0):
    print(str.ljust("Threshold not configured", col1 + col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
else:
    print(str.ljust("Threshold:", col1) + str.ljust(csymb + str(threshold), col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
print()
print(delimiter)
print()
while True:

    # Get current prices / times - on first run set comparison variables to == first batch of data


    try:
        stockprice = round(si.get_live_price(symbol), 2)
        if (currency == "usd"):
            currval = 1
        else:
            currval = round(si.get_live_price(currency + "usd=x"), 4)
    except requests.exceptions.ConnectionError as ex:
        if firstrun:
            print("Cannot connect to server, wifi on buddy?")
            print()
            quit()
        else:
            print("Cannot connect to server, call yourself an engineer? Using last known price")
            print()
    except requests.exceptions.ReadTimeout as ex:
        if firstrun:
            print("Timeout connecting to server, half day working?")
            print()
            quit()
        else:
            print("Timeout connecting to server, better use the last price")
            print()
    except AssertionError as ex:
        if firstrun:
            print("Call yourself a financial wizard? Try picking a real stock")
            print()
            quit()
        else:
            print("Something went horribly wrong on the far end. I blame Brexit!")
            print()


    now = datetime.now()
    EST = datetime.now(timezone('America/New_York'))
    currequiv = round(stockprice/currval, 2)
    value = round(multiplier * currequiv, 2)
    if not firstrun:
        vdelta = str(round((value / bestvalue - 1) * 100,2)) + "%"
        pdelta = str(round((stockprice / bestprice - 1) * 100, 2)) + "%"
        fdelta = str(round((currval / lowfx -1) * 100, 2)) + "%"
    else:
        lowfx = currval

    # If price/FX rate has moved then set new best rates

    if stockprice > bestprice:
        bestprice = stockprice
    if currval < lowfx:
        lowfx = currval

    # Tick-tock format of start time line - just to show script is iterating

    if ticktock:
        print(str.ljust("Start:", col1) + "\33[44m" + str.ljust(starttime , col2) + "\33[0m" + str.ljust(starttimeEST + " EST", col3) + str.rjust(startdate, col4a))
        ticktock = False
    else:
        print(str.ljust("Start:", col1) + str.ljust(starttime, col2) + "\33[44m" + str.ljust(starttimeEST + " EST", col3) + "\33[0m" + str.rjust(startdate, col4a))
        ticktock = True

    # Print basic live data

    print(str.ljust("Time:", col1) + str.ljust(now.strftime("%H:%M:%S"), col2) + str.ljust(EST.strftime("%H:%M:%S") + " EST", col3))
    print()
    print(str.ljust(symbol.upper() + ":", col1) + str.ljust("$" + str(stockprice), col2) + str.ljust("(" + str(bestprice) + " High)",col3) + str.rjust(pdelta,col4a))
    if (currency != "usd"):
        print(str.ljust(currency.upper() + ":", col1) + str.ljust("x" + str(currval), col2) + str.ljust("(" + str(lowfx) + " Low)",col3) + str.rjust(fdelta,col4a))
        print(str.ljust("PRICE:", col1) + str.ljust(csymb + str(currequiv),col2))

    # Format value line - colour code & sheel beep alerts depending on case

    if firstrun:
        print(str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2))
    else:
        if (threshold != 0):
            if (multiplier * currequiv > threshold): 
                print('\33[42m' + str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b) + '\33[0m' + '\a\a\a')
            elif (value > bestvalue):
                print('\33[7m' + str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b) + '\33[0m')
            else:
                print(str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b))
        else:
            if (value > bestvalue):
                print('\33[7m' + str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b) + '\33[0m')
            else:
                print(str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b))

    # Format best-since-start line - the highest price * value in local currency during run time. Alert if best increases

    if firstrun:
        bestvalue = value
        print(str.ljust("BEST:", col1) + str.ljust(csymb + str(bestvalue), col2))
    elif (value > bestvalue):
        bestvalue = value
        print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value) + '\33[0m' + '\a', col2))
    elif (value == bestvalue):
        print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value) + '\33[0m', col2))
    else:
        print(str.ljust("BEST:", col1) + str.ljust(csymb + str(bestvalue), col2))
    firstrun = False
    print()


    # Generate countdown timer

    for i in range(refresh):
        sys.stdout.write("\r" + str.center("--- Refreshes in " + str(refresh - i) + " seconds ---",maxwidth))
        sys.stdout.flush()
        time.sleep(1)
    print(delimiter)
    print()

