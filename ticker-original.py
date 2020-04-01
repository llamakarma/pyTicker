#!/usr/bin/env python3.6

# Requires Python 3.6+
# Package / help information

version = "20200331-08"
helpnotes= """Hot-keys during use:

Q/q - quit
R/r - reset baselines
U/u - up = increase threshold by -p %
      (if !-t, !-p, units of 100 currency, if -p, !-t, units of 100 x p)
D/d - down = decrease threshold by -p %
      (if !-t, !-p, units of 100 currency, if -p, !-t, units of 100 x p)
F/f - faster = decrease refresh interval
S/s - slower = increase refresh interval
T/t - print threshold
B/b - toggle alert bell

Note: Only one keypress per iteration is actioned. Multiple keypresses will be queued
and implemented on subsequent iterations.

Example usage:

Track Apple stock natively in $USD           ./ticker.py -s aapl
Track Apple stock in £GBP                    ./ticker.py -s aapl -c gbp
Track the GBP-USD exchange rate              ./ticker.py -s usdgbp=x -c gbp -b
Track the value of 85 Apple shares in €EUR   ./ticker.py -s aapl -c eur -m 85
Set an alert threshold of $750/share         ./ticker.py -s aapl -t 750
Set an alert for £10k on 10 Tesla shares     ./ticker.py -s tsla -c gbp -m 10 -t 10000
Make the ticker update every 5 seconds       ./ticker.py -s tsla -c gbp -m 10 -t 10000 -i 5
Write updates to a CSV file                  ./ticker.py -s tsla -c eur -m 10 -t 10000 -o output.csv -i 5
Threshold increments of $200 (no -t)         ./ticker.py -s aapl -p 2
Threshold set at start, increments of 5%     ./ticker.py -s aapl -tv -p 5


Alerts:

Ensure you have system sounds enabled for your terminal/volume turned up!

1 x bong      - new high value since init/re-init
3 x bongs     - value is over your threshold (if configured)

New features in recent memory:

- USD support (i.e. 1:1 exchange rate, hide currency conversion)
- Replace mandatory parameters with defaults, provide easy access variables to adjust
- Code tidy up/comments
- Revised some outputs
- Handle Yahoo API exceptions better (thanks Flacko)
- Added time of peak stock/lowest FX values/best value
- Added hotkeys
- Added write out to CSV
- Added parameter to disable price / value / best
  (also enables bell alerts on stock price instead of value)
- Added bell toggle notification and bell status to countdown
- Added auto-threshold based on opening value


To do list:

- Improve argsparse usage with defaults / cut down if-else for argument handling
- Pylint -> proper code cleanup

\n\n
"""

# Cmdline parameter defaults

defcurrency = "usd"
defsymbol = "^gspc"
defmulti = 1
defthresh = 0
defrefresh = 20
defthreshfactor = 5
defrefreshincrement = 5
defbell = "\a"
defmultibell = "\a\a\a"
defrndval = 4

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

from json import JSONDecodeError
from select import select
from datetime import datetime
from pytz import timezone
from yahoo_fin import stock_info as si

# Handle puke

def signal_handler(sig, frame):
    print()
    print()
    print('Thanks for all the fish, smeg head.')
    print()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Keystroke listener

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
        dr, dw, de = select([sys.stdin], [], [], 0)
        return dr != []


def main():
    # Get command line parameters

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description = "pyTicker version " + version,
        epilog = helpnotes)
    parser.add_argument("-s", type=str, help="stock symbol to watch (default " + defsymbol.upper() + ")")
    parser.add_argument("-c", choices=["eur", "gbp", "usd", "zar"], type=str, help="select threshold/value currency (default " + defcurrency.upper() + ")")
    parser.add_argument("-m", type=int, help="multiplier (Price x Multiplier = Value) (default " + str(defmulti) + ")")
    parser.add_argument("-t", type=int, help="threshold value for alerts (default disabled)")
    parser.add_argument("-tv", action='store_true', default=False, help="threshold = opening Price x Multiplier (if !-p, 1%%)")
    parser.add_argument("-p", type=int, help="threshold hotkey (u/d) ± in %% of threshold (default " + str(defthreshfactor) + ")")
    parser.add_argument("-i", type=int, help="refresh interval in seconds (default " + str(defrefresh) + ")")
    parser.add_argument("-r", type=int, help="refresh hotkey (f/s) ± in seconds (default " + str(defrefreshincrement) + ")")
    parser.add_argument("-d", type=int, help="number of decimal places for stock and currency prices (default " + str(defrndval) + ")")
    parser.add_argument("-o", type=str, help="CSV output file (default disabled)")
    parser.add_argument("-b", action='store_false', default=True, help="brief output - disable Price, Value, Best") 

    args = parser.parse_args()

    # Setup basic variables based on parameters or defaults

    if args.c == None:
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
    if args.s == None:
        symbol = defsymbol
    else:
        symbol = args.s
    if args.m == None:
        multiplier = defmulti
    else:
        multiplier = args.m
    if args.t == None:
        threshold = defthresh
    else:
        threshold = args.t
    bestvalue = 0
    if args.i == None:
        refresh = defrefresh
    else:
        refresh = args.i
    if args.o == None:
        outfile = "" 
    else:
        outfile = args.o
    if args.r == None:
        refreshincrement = defrefreshincrement
    else:
        refreshincrement = args.r
    if args.p == None:
        if threshold == 0 and not args.tv:
            thresholdchange = 100
        else:
            thresholdchange = threshold * defthreshfactor / 100
    else:
        if threshold == 0:
            thresholdchange = args.p * 100
        else:
            thresholdchange = threshold * args.p / 100
    if args.d == None:
        rndval = defrndval
    else:
        rndval = args.d

# Precedence in case user requests both -t and -tv arguments

    if args.t != None and args.tv:
        args.tv = False

    CSVfile = ""
    vdelta = ""
    pdelta = ""
    fdelta = ""
    bestprice = 0
    lastbestprice = 0
    lowfx = 0
    bell = defbell
    multibell = defmultibell

    # Flags for conditional formatting

    firstrun = True
    ticktock = True

    # Collect start of first run

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

    # Generate CSV header and delimiter line between iterations based on output width

    csvhdr = "Status,StartTime,StartTimeEST,Date,Symbol,SymbolPrice,SymbolHigh,SymbolHighTime,Currency,CurrencyValue,CurrencyLow,CurrencyLowTime,Value,BestValue,BestValueTime\n"
    csvstr = ""
    delimiter = "\r"
    for i in range(maxwidth):
        delimiter = delimiter + "-"

    # Init key listener

    keystroke = KBHit()

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
                print("\33[44m" + str.center("--- Increase threshold to " + csymb + str(round(threshold, 2)) + " ---", maxwidth) + "\33[0m")
                print()
            elif ( c == "D" ) or ( c == "d" ): # Down threshold
                if (threshold - thresholdchange <= 0):
                    threshold = 0
                else:
                    threshold = threshold - thresholdchange
                print("\33[44m" + str.center("--- Reduce threshold to " + csymb + str(round(threshold, 2)) + " ---", maxwidth) + "\33[0m")
                print()
            elif ( c == "F" ) or ( c == "f" ): # Faster iteration
                if refresh - refreshincrement <= 2:
                    refresh = refreshincrement
                else:
                    refresh = refresh - refreshincrement
            elif ( c == "S" ) or ( c == "s" ): # Slower iteration
                refresh = refresh + refreshincrement
            elif ( c == "T" ) or ( c == "t" ): # Print current threshold
                print("\33[44m" + str.center("--- Current threshold is " + csymb + str(round(threshold, 2)) + " ---", maxwidth) + "\33[0m")
                print()
            elif ( c == "B" ) or ( c == "b"): # Toggle bell
                if bell != defbell:
                    bell = defbell
                    multibell = defmultibell
                    print("\33[44m" + str.center("--- Alerts enabled ---", maxwidth) + "\33[0m")
                    print()
                else:
                    bell = ""
                    multibell = ""
                    print("\33[44m" + str.center("--- Alerts disabled ---", maxwidth) + "\33[0m")
                    print()
            else:
                pass

    # Print startup / re-init header

        if firstrun:
            print()
            print(str.ljust("Version:", col1) + str.ljust(version, col2) + str.ljust("Stock:", col3) + str.rjust(symbol.upper(), col4a ))
            print(str.ljust("Multiple:", col1) + str.ljust(str(multiplier), col2) + str.ljust("Currency:", col3) + str.rjust("(" + csymb + ") " + currency.upper(), col4a))

            if args.tv:
                print(str.ljust("Threshold at open value", col1 + col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
            elif (threshold == 0):
                print(str.ljust("Threshold not configured", col1 + col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
            else:
                print(str.ljust("Threshold:", col1) + str.ljust(csymb + str(threshold), col2) + str.ljust("Interval:", col3) + str.rjust(str(refresh), col4a))
            print()
            print("\33[44m" + delimiter + "\33[m")
            print()

    # Get current prices / times - on first run set comparison variables to == first batch of data

        try:
            stockprice = round(si.get_live_price(symbol), rndval)
            if firstrun:
                lastbestprice = bestprice = stockprice
            if (currency == "usd"):
                currval = 1
            else:
                currval = round(si.get_live_price(currency + "usd=x"), rndval)
            if not outfile == "":
                if os.path.exists(outfile):
                    CSVfile = open(outfile, "a")
                else:
                    CSVfile = open(outfile, "w")
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

    # Get time and stock prices

        now = datetime.now()
        now = now.strftime("%H:%M:%S")
        EST = datetime.now(timezone('America/New_York'))
        EST = EST.strftime("%H:%M:%S")
        currequiv = round(stockprice/currval, rndval)
        if not firstrun:
            value = round(multiplier * currequiv, 2)
            vdelta = str(round((value / bestvalue - 1) * 100, 2)) + "%"
            pdelta = str(round((stockprice / bestprice - 1) * 100, 2)) + "%"
            fdelta = str(round((currval / lowfx -1) * 100, 2)) + "%"
        else:
            lowfx = currval
            value = bestvalue = round(multiplier * currequiv, 2)
            if args.tv:
                threshold = value
                if args.p == None:
                    thresholdchange = value / 100
                else:
                    thresholdchange = threshold * args.p / 100


    # If price/FX rate has moved then set new best rates

        if stockprice > bestprice:
            lastbestprice = bestprice
            bestprice = stockprice
            peakstocktime = now
        if currval < lowfx:
            lowfx = currval
            lowfxtime = now

    # Tick-tock format of start time line - just to show quickly that the script is iterating

        if ticktock:
            print("\33[44m" + str.ljust("Start:", col1) + "\33[0m" + str.ljust(starttime, col2) + str.ljust(starttimeEST + " EST", col3) + str.rjust(startdate, col4a + col5))
            ticktock = False
        else:
            print(str.ljust("Start:", col1) + str.ljust(starttime, col2) + str.ljust(starttimeEST + " EST", col3) + str.rjust(startdate, col4a + col5))
            ticktock = True

    # Print basic live data

        print(str.ljust("Time:", col1) + str.ljust(now, col2) + str.ljust(EST + " EST", col3))
        print()

        if not args.b and bestprice > lastbestprice:
            print('\33[7m' + str.ljust(symbol.upper() + ":", col1) + str.ljust("$" + str(stockprice), col2) + str.ljust("H: " + str(bestprice), col3) + str.rjust(pdelta, col4a) + str.rjust("@ " + peakstocktime, col5) + '\33[0m' + bell)
            lastbestprice = bestprice
        else:
            print(str.ljust(symbol.upper() + ":", col1) + str.ljust("$" + str(stockprice), col2) + str.ljust("H: " + str(bestprice), col3) + str.rjust(pdelta, col4a) + str.rjust("@ " + peakstocktime, col5))
        if currency != "usd":
            print(str.ljust(currency.upper() + ":", col1) + str.ljust("x" + str(currval), col2) + str.ljust("L: " + str(lowfx), col3) + str.rjust(fdelta, col4a) + str.rjust("@ " + lowfxtime, col5))
        if currency != "usd" and args.b:
            print(str.ljust("PRICE:", col1) + str.ljust(csymb + str(currequiv), col2))

    # Format value line - colour code & shell beep alerts depending on case

        if args.b:
            if firstrun:
                print(str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2))
            else:
                if (threshold != 0):
                    if (multiplier * currequiv > threshold): 
                        print('\33[42m' + str.ljust("VALUE:", col1) + str.ljust(csymb + str(value), col2) + str.rjust(vdelta, col4b) + '\33[0m' + multibell)
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
                print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value), col2) + str.rjust("@ " + peakvaluetime, col4b + col5) + '\33[0m' + bell)
            elif (value == bestvalue):
                print('\33[7m' + str.ljust("BEST:", col1) + str.ljust(csymb + str(value), col2) + str.rjust("@ " + peakvaluetime, col4b + col5) + '\33[0m')
            else:
                print(str.ljust("BEST:", col1) + str.ljust(csymb + str(bestvalue), col2) + str.rjust("@ " + peakvaluetime, col4b + col5))


    # For reference: csvhdr = "Status,StartTime,StartTimeEST,Date,Symbol,SymbolPrice,SymbolHigh,SymbolHighTime,Currency,CurrencyValue,CurrencyLow,CurrencyLowTime,Value,BestValue,BestValueTime"

        csvstr = now + "," + EST + "," + startdate + "," + symbol + "," + str(stockprice) + "," + str(bestprice) + "," + peakstocktime + "," + currency + "," + str(currval) + "," + str(lowfx) + "," + lowfxtime + "," + str(value) + "," + str(bestvalue) + "," + peakvaluetime
        if not outfile == "":
            if firstrun:
                csvstr = "Start," + csvstr + "\n"
                CSVfile.write(csvhdr)
            else:
                csvstr = "Run," + csvstr + "\n"
            CSVfile.write(csvstr)
            CSVfile.close()
        firstrun = False
        print()

    # Generate countdown timer

        for i in range(refresh):
            if bell == "":
                sys.stdout.write("\r" + str.center("--- Refreshes in " + str(refresh - i) + " seconds ---", maxwidth))
                sys.stdout.flush()
                time.sleep(1)
            else:
                sys.stdout.write("\r" + str.center("-" + u'\U0001f514' + "- Refreshes in " + str(refresh - i) + " seconds -" + u'\U0001f514' + "-", maxwidth))
                sys.stdout.flush()
                time.sleep(1)
        print(delimiter)
        print()

    # Normal termination activities

    keystroke.set_normal_term()
    if not outfile == "":
        CSVfile.close()
    quit()

if __name__ == '__main__':
    main()
