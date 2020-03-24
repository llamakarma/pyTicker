#!/usr/bin/env python3.6

# Requires Python 3.6

# Package information

version = "20200324-08"
helpnotes= """Hot-keys during use:

Q/q - quit
R/r - reset baselines
U/u - increase threshold by 10% of original
D/d - decrease threshold by 10% of original


New features this release:

- USD support (i.e. 1:1 exchange rate, hide currency conversion)
- Replace mandatory parameters with defaults, provide easy access variables to adjust
- Code tidy up/comments
- Revised some outputs
- Handle Yahoo API exceptions better (thanks Flacko)
- Added time of peak stock/lowest FX values/best value
- Added hotkeys
\n\n
"""

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
import os
import termios
import atexit
from select import select


from datetime import datetime
from pytz import timezone
from yahoo_fin import stock_info as si

# Handle puke

#os.system("stty -echo")

def signal_handler(sig, frame):
    print()
    print()
    print('Thanks for all the fish, smeg head.')
    print()
#    os.system("stty echo")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


class KBHit:

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.new_term = termios.tcgetattr(self.fd)
        self.old_term = termios.tcgetattr(self.fd)

        # New terminal setting unbuffered
        self.new_term[3] = (self.new_term[3] & ~termios.ICANON & ~termios.ECHO)
        termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

        # Support normal-terminal reset at exit
        atexit.register(self.set_normal_term)

    def set_normal_term(self):
        termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        return sys.stdin.read(1)

    def kbhit(self):
        dr,dw,de = select([sys.stdin], [], [], 0)
        return dr != []




# Get command line parameters

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description = "pyTicker version " + version,
    epilog = helpnotes)
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
thresholdchange = threshold / 10
startdate = datetime.now()
startdate = startdate.strftime("%d-%m-%Y")
starttime = datetime.now()
starttime = starttime.strftime("%H:%M:%S")
peakvaluetime = starttime
peakstocktime = starttime
lowfxtime = starttime
starttimeEST = datetime.now(timezone('America/New_York'))
starttimeEST = starttimeEST.strftime("%H:%M:%S")

# Set column widths

col1 = 15
if (len(str(threshold)) < 10):
    col2 = 15
else:
    col2 = len(str(threshold)) + 5
col3 = 14
col4a = 10
col4b = col4a + col3
col5 = 14
maxwidth = col1 + col2 + col3 + col4a + col5

# Generate delimiter line between iterations based on output width
keystroke = KBHit()
delimiter = "\r"
for i in range(maxwidth):
    delimiter = delimiter + "-"

# Go!
while True:

# Check hotkeys

    if keystroke.kbhit():
        c = keystroke.getch()
        if ( c == "Q" ) or ( c == "q" ): # Quit
            print()
            print("Thanks for all the fish, smeg head.")
            print()
            break
        elif ( c == "R" ) or ( c == "r" ): # Reset
            firstrun = True
            startdate = datetime.now()
            startdate = startdate.strftime("%d-%m-%Y")
            starttime = datetime.now()
            starttime = starttime.strftime("%H:%M:%S")
            peakvaluetime = starttime
            peakstocktime = starttime
            lowfxtime = starttime
            starttimeEST = datetime.now(timezone('America/New_York'))
            starttimeEST = starttimeEST.strftime("%H:%M:%S")
            vdelta = ""
            pdelta = ""
            fdelta = ""
        elif ( c == "U" ) or ( c == "u" ): # Up threshold
            threshold = threshold + thresholdchange
            print("\33[44m" + str.center("--- Increase threshold to " + csymb + str(threshold) + " ---",maxwidth) + "\33[0m")
            print()
        elif ( c == "D" ) or ( c == "d" ): # Down threshold
            threshold = threshold - thresholdchange
            print("\33[44m" + str.center("--- Reduce threshold to " + csymb + str(threshold) + " ---",maxwidth) + "\33[0m")
            print()
        else:
            pass

# Print header

    if firstrun:
        print(str.ljust("Version:", col1) + str.ljust(version, col2) + str.ljust("Stock:", col3) + str.rjust(symbol.upper(), col4a ))
        print(str.ljust("Multiple:", col1) + str.ljust(str(multiplier), col2) + str.ljust("Currency:", col3) + str.rjust("(" + csymb + ") " + currency.upper(), col4a))
        if (threshold == 0):
            print(str.ljust("Threshold not configured", col1 + col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
        else:
            print(str.ljust("Threshold:", col1) + str.ljust(csymb + str(threshold), col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
        print()
        print("\33[44m" + delimiter + "\33[m")
        print()

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
    except JSONDecodeError as ex:
        if firstrun:
            print("There's a glitch in the matrix - can't read the market API - please try again")
            print()
            quit()
        else:
            print("There's a glitch in the matrix - can't reach the market API - trying again")
            print()



    now = datetime.now()
    now = now.strftime("%H:%M:%S")
    EST = datetime.now(timezone('America/New_York'))
    EST = EST.strftime("%H:%M:%S")
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
        peakstocktime = now
    if currval < lowfx:
        lowfx = currval
        lowfxtime = now

    # Tick-tock format of start time line - just to show script is iterating

    if ticktock:
        print("\33[44m" + str.ljust("Start:", col1) + "\33[0m" + str.ljust(starttime, col2) + str.ljust(starttimeEST + " EST", col3) + str.rjust(startdate, col4a + col5))
        ticktock = False
    else:
        print(str.ljust("Start:", col1) + str.ljust(starttime, col2) + str.ljust(starttimeEST + " EST", col3) + str.rjust(startdate, col4a + col5))
        ticktock = True

    # Print basic live data

    print(str.ljust("Time:", col1) + str.ljust(now, col2) + str.ljust(EST + " EST", col3))
    print()
    print(str.ljust(symbol.upper() + ":", col1) + str.ljust("$" + str(stockprice), col2) + str.ljust("H: " + str(bestprice), col3) + str.rjust(pdelta,col4a) + str.rjust("@ " + peakstocktime, col5))
    if (currency != "usd"):
        print(str.ljust(currency.upper() + ":", col1) + str.ljust("x" + str(currval), col2) + str.ljust("L: " + str(lowfx), col3) + str.rjust(fdelta,col4a) + str.rjust("@ " + lowfxtime, col5))
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
        print(str.ljust("BEST:", col1) + str.ljust(csymb + str(bestvalue), col2) + str.rjust("@ " + peakvaluetime, col4b + col5))
    elif (value > bestvalue):
        bestvalue = value
        peakvaluetime = now
        print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value), col2) + str.rjust("@ " + peakvaluetime, col4b + col5) + '\33[0m' + '\a')
    elif (value == bestvalue):
        print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value), col2) + str.rjust("@ " + peakvaluetime, col4b + col5) + '\33[0m')
    else:
        print(str.ljust("BEST:", col1) + str.ljust(csymb + str(bestvalue), col2) + str.rjust("@ " + peakvaluetime, col4b + col5))
    firstrun = False
    print()


    # Generate countdown timer

    for i in range(refresh):
        sys.stdout.write("\r" + str.center("--- Refreshes in " + str(refresh - i) + " seconds ---",maxwidth))
        sys.stdout.flush()
        time.sleep(1)
    print(delimiter)
    print()

keystroke.set_normal_term()
quit()
