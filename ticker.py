#!/usr/bin/env python3.6

"""This script reads stock prices iteratively and allows the user to convert currencies, create
alerts, set alarm thresholds and more."""

# Requires Python 3.6+
# Package / help information

# Libraries

import signal
import sys
import time
import argparse
import os
import termios
import atexit

from json import JSONDecodeError
from select import select
from datetime import datetime

import requests
import requests_html
import requests_cache

from yahoo_fin import stock_info as si
from pytz import timezone


VERSION = "20200513-01"
HELP_NOTES = """Hot-keys during use:

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
Write updates to a CSV file                  ./ticker.py -s tsla -c eur -m 10 -t 600 -o out.csv -i 5
Threshold increments of $200 (no -t)         ./ticker.py -s aapl -p 2
Threshold set at start, increments of 5%     ./ticker.py -s aapl -tv -p 5


Alerts:

Ensure you have system sounds enabled for your terminal/volume turned up!

1 x bong      - new high value since init/re-init
3 x bongs     - value is over your threshold (if configured)

New features in recent memory:

- USD support (i.e. 1:1 exchange rate, hide currency conVERSION)
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
- Added quiet mode startup
- Added Requests-Cache


To do list:

- Refactor

\n\n
"""

# Cmdline parameter defaults

DEF_CURRENCY = "usd"
DEF_SYMBOL = "^gspc"
DEF_MULTI = 1
DEF_THRESH = 0.0
DEF_REFRESH = 20
DEF_THRESH_FACTOR = 5
DEF_REFRESH_INC = 5
DEF_BELL = "\a"
DEF_MULTI_BELL = "\a\a\a"
DEF_RND_VAL = 4
CSV_HDR = "Status,StartTime,StartTimeEST,Date,Symbol,SymbolPrice,SymbolHigh,SymbolHighTime," \
          "Currency,CurrencyValue,CurrencyLow,CurrencyLowTime,Value,BestValue,BestValueTime\n"


# Handle puke
# noinspection PyUnusedLocal
def signal_handler(sig, frame):
    print()
    print()
    print('Thanks for all the fish, smeg head.')
    print()
    sys.exit(1)


signal.signal(signal.SIGINT, signal_handler)


# Keystroke listener
class KBHit:

    def __init__(self):
        self.f_d = sys.stdin.fileno()
        self.new_term = termios.tcgetattr(self.f_d)
        self.old_term = termios.tcgetattr(self.f_d)


# New terminal setting unbuffered
        self.new_term[3] = (self.new_term[3] & ~termios.ICANON & ~termios.ECHO)
        termios.tcsetattr(self.f_d, termios.TCSAFLUSH, self.new_term)

# Support normal-terminal reset at exit
        atexit.register(self.set_normal_term)

    def set_normal_term(self):
        termios.tcsetattr(self.f_d, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        return sys.stdin.read(1)

    def kbhit(self):
        d_r, d_w, d_e = select([sys.stdin], [], [], 0)
        return d_r != []


def write_csv_file(first_run, csv_str, csv_file):
    if first_run:
        csv_file.write(CSV_HDR)
        csv_str = "Start," + csv_str + "\n"
    else:
        csv_str = "Run," + csv_str + "\n"
    csv_file.write(csv_str)
    csv_file.close()


def make_delimiter(max_width):
    delimiter = "\r"
    for i in range(max_width):
        delimiter = delimiter + "-"
    return delimiter


def print_countdown(bell, refresh, max_width):
    for i in range(refresh):
        if bell == "":
            sys.stdout.write("\r" + str.center("--- Refreshes in " + str(refresh - i) +
                                               " seconds ---", max_width))
            sys.stdout.flush()
            time.sleep(1)
        else:
            sys.stdout.write("\r" + str.center("-" + u'\U0001f514' + "- Refreshes in " +
                                               str(refresh - i) + " seconds -" + u'\U0001f514' +
                                               "-", max_width))
            sys.stdout.flush()
            time.sleep(1)


def set_column_width(threshold):
    col = [0] * 5
    col[0] = 15
    if len(str(threshold)) < 10:
        col[1] = 15
    else:
        col[1] = len(str(threshold)) + 5
    col[2] = 14
    col[3] = 10
    col[4] = 14
    return col

def parse_cmdline():

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description="pyTicker version " + VERSION,
                                     epilog=HELP_NOTES)
    parser.add_argument("-s", type=str, help="stock symbol to watch (default " + DEF_SYMBOL.upper()
                        + ")")
    parser.add_argument("-c", choices=["eur", "gbp", "usd", "zar"], type=str,
                        help="select threshold/value currency (default " + DEF_CURRENCY.upper()
                        + ")")
    parser.add_argument("-m", type=int, help="multiplier (Price x Multiplier = Value) (default " +
                        str(DEF_MULTI) + ")")
    parser.add_argument("-t", type=int, help="threshold value for alerts (default disabled)")
    parser.add_argument("-tv", action='store_true', default=False,
                        help="threshold = opening Price x Multiplier "
                        "(if !-p, 1%% hotkey adjustments)")
    parser.add_argument("-p", type=int, help="threshold hotkey (u/d) ± in %% of threshold (default "
                        + str(DEF_THRESH_FACTOR) + ")")
    parser.add_argument("-i", type=int, help="refresh interval in seconds (default " +
                        str(DEF_REFRESH) + ")")
    parser.add_argument("-r", type=int, help="refresh hotkey (f/s) ± in seconds (default " +
                        str(DEF_REFRESH_INC) + ")")
    parser.add_argument("-d", type=int, help="number of decimal places for stock and currency "
                        "prices (default " + str(DEF_RND_VAL) + ")")
    parser.add_argument("-o", type=str, help="CSV output file (default disabled)")
    parser.add_argument("-b", action='store_false', default=True, help="brief output - disable "
                        "Price, Value, Best")
    parser.add_argument("-q", action='store_true', default=False, help="quiet mode - disable bell on startup")
    return parser.parse_args()


def main():
    """ Main """

    # Get command line parameters

    args = parse_cmdline()

    # Setup basic variables based on parameters or defaults

    if args.c is None:
        currency = DEF_CURRENCY
    else:
        currency = args.c
    if currency == "gbp":
        c_symb = "£"
    elif currency == "eur":
        c_symb = "€"
    elif currency == "zar":
        c_symb = "R"
    elif currency == "usd":
        c_symb = "$"
    else:
        c_symb = "#"
    if args.s is None:
        symbol = DEF_SYMBOL
    else:
        symbol = args.s
    if args.m is None:
        multiplier = DEF_MULTI
    else:
        multiplier = args.m
    if args.t is None:
        threshold = DEF_THRESH
    else:
        threshold = args.t
    best_value = 0
    if args.i is None:
        refresh = DEF_REFRESH
    else:
        refresh = args.i
    if args.o is None:
        out_file = ""
    else:
        out_file = args.o
    if args.r is None:
        refresh_inc = DEF_REFRESH_INC
    else:
        refresh_inc = args.r
    if args.p is None:
        if threshold == 0 and not args.tv:
            thresh_change = 100
        else:
            thresh_change = threshold * DEF_THRESH_FACTOR / 100
    else:
        if threshold == 0:
            thresh_change = args.p * 100
        else:
            thresh_change = threshold * args.p / 100
    if args.d is None:
        rnd_val = DEF_RND_VAL
    else:
        rnd_val = args.d
    if args.q:
        bell = ""
        multi_bell = ""
    else:
        bell = DEF_BELL
        multi_bell = DEF_MULTI_BELL

# Precedence in case user requests both -t and -tv arguments

    if args.t is not None and args.tv:
        args.tv = False

    csv_file = ""
    val_delta = ""
    price_delta = ""
    fx_delta = ""
    best_price = 0
    last_best_price = 0
    low_fx = 0

    # Flags for conditional formatting

    first_run = True
    tick_tock = True
    quit_flag = False

    # Collect start of first run

    start_date = datetime.now()
    start_date = start_date.strftime("%d-%m-%Y")
    start_time = datetime.now()
    start_time = start_time.strftime("%H:%M:%S")
    peak_val_time = start_time
    peak_stk_time = start_time
    low_fx_time = start_time
    start_time_est = datetime.now(timezone('America/New_York'))
    start_time_est = start_time_est.strftime("%H:%M:%S")

    # Init key listener

    keystroke = KBHit()

    # Setup requests_cache to limit DNS queries. Unique cache name required to prevent DB collision
    # between multiple instances. Could use random, probably not required.

    requests_cache.install_cache('ticker_cache_' + start_time)

    # Go!

    while not quit_flag:

        #  Figure out column widths based on threshold and generate delimiter bar

        col = set_column_width(threshold)
        delimiter = make_delimiter(sum(col))

    # Print startup / re-init header

        if first_run:
            print()
            print(str.ljust("Version:", col[0]) + str.ljust(VERSION, col[1]) +
                  str.ljust("Stock:", col[2]) + str.rjust(symbol.upper(), col[3]))
            print(str.ljust("Multiple:", col[0]) + str.ljust(str(multiplier), col[1]) +
                  str.ljust("Currency:", col[2]) + str.rjust("(" + c_symb + ") " +
                                                             currency.upper(), col[3]))

            if args.tv:
                print(str.ljust("Threshold at open value", col[0] + col[1]) +
                      str.ljust("Interval:", col[2]) + str.rjust(str(refresh), col[3]))
            elif threshold == 0:
                print(str.ljust("Threshold not configured", col[0] + col[1]) +
                      str.ljust("Interval:", col[2]) + str.rjust(str(refresh), col[3]))
            else:
                print(str.ljust("Threshold:", col[0]) + str.ljust(c_symb + str(threshold), col[1]) +
                      str.ljust("Interval:", col[2]) + str.rjust(str(refresh), col[3]))
            print()
            print("\33[44m" + delimiter + "\33[m")
            print()

    # Get current prices / times - on first run set comparison variables to == first batch of data

        try:
            stock_price = round(si.get_live_price(symbol), rnd_val)
            if first_run:
                last_best_price = best_price = stock_price
            if currency == "usd":
                curr_val = 1
            else:
                curr_val = round(si.get_live_price(currency + "usd=x"), rnd_val)
            if out_file != "":
                if os.path.exists(out_file):
                    csv_file = open(out_file, "a")
                else:
                    csv_file = open(out_file, "w")
        except requests.exceptions.ConnectionError as ex:
            if first_run:
                print("Cannot connect to server, wifi on buddy?")
                print()
                sys.exit(3)
            else:
                print("Cannot connect to server, call yourself an engineer? Using last known price")
                print()
        except requests.exceptions.ReadTimeout as ex:
            if first_run:
                print("Timeout connecting to server, half day working?")
                print()
                sys.exit(3)
            else:
                print("Timeout connecting to server, better use the last price")
                print()
        except AssertionError as ex:
            if first_run:
                print("Call yourself a financial wizard? Try picking a real stock")
                print()
                sys.exit(3)
            else:
                print("Something went horribly wrong on the far end. I blame Brexit!")
                print()
        except JSONDecodeError as ex:
            if first_run:
                print("There's a glitch in the matrix - can't read the market API - "
                      "please try again")
                print()
                sys.exit(3)
            else:
                print("There's a glitch in the matrix - can't reach the market API - trying again")
                print()

    # Get time and stock prices

        now = datetime.now()
        now = now.strftime("%H:%M:%S")
        est_time = datetime.now(timezone('America/New_York'))
        est_time = est_time.strftime("%H:%M:%S")
        curr_equiv = round(stock_price/curr_val, rnd_val)
        if not first_run:
            value = round(multiplier * curr_equiv, 2)
            val_delta = str(round((value / best_value - 1) * 100, 2)) + "%"
            price_delta = str(round((stock_price / best_price - 1) * 100, 2)) + "%"
            fx_delta = str(round((curr_val / low_fx - 1) * 100, 2)) + "%"
        else:
            low_fx = curr_val
            value = best_value = round(multiplier * curr_equiv, 2)
            if args.tv:
                threshold = value
                if args.p is None:
                    thresh_change = value / 100
                else:
                    thresh_change = threshold * args.p / 100

    # If price/FX rate has moved then set new best rates

        if stock_price > best_price:
            last_best_price = best_price
            best_price = stock_price
            peak_stk_time = now
        if curr_val < low_fx:
            low_fx = curr_val
            low_fx_time = now

    # Tick-tock format of start time line - just to show quickly that the script is iterating

        if tick_tock:
            print("\33[44m" + str.ljust("Start:", col[0]) + "\33[0m" + str.ljust(start_time, col[1])
                  + str.ljust(start_time_est + " EST", col[2]) + str.rjust(start_date, col[3] +
                                                                           col[4]))
            tick_tock = False
        else:
            print(str.ljust("Start:", col[0]) + str.ljust(start_time, col[1]) +
                  str.ljust(start_time_est + " EST", col[2]) + str.rjust(start_date, col[3] +
                                                                         col[4]))
            tick_tock = True

    # Print basic live data

        print(str.ljust("Time:", col[0]) + str.ljust(now, col[1]) + str.ljust(est_time + " EST",
                                                                              col[2]))
        print()

        if not args.b and best_price > last_best_price:
            print('\33[7m' + str.ljust(symbol.upper() + ":", col[0]) +
                  str.ljust("$" + str(stock_price), col[1]) +
                  str.ljust("H: " + str(best_price), col[2]) + str.rjust(price_delta, col[3]) +
                  str.rjust("@ " + peak_stk_time, col[4]) + '\33[0m' + bell)
            last_best_price = best_price
        else:
            print(str.ljust(symbol.upper() + ":", col[0]) + str.ljust("$" + str(stock_price),
                                                                      col[1]) +
                  str.ljust("H: " + str(best_price), col[2]) + str.rjust(price_delta, col[3]) +
                  str.rjust("@ " + peak_stk_time, col[4]))
        if currency != "usd":
            print(str.ljust(currency.upper() + ":", col[0]) + str.ljust("x" + str(curr_val),
                                                                        col[1]) +
                  str.ljust("L: " + str(low_fx), col[2]) + str.rjust(fx_delta, col[3]) +
                  str.rjust("@ " + low_fx_time, col[4]))
        if currency != "usd" and args.b:
            print(str.ljust("PRICE:", col[0]) + str.ljust(c_symb + str(curr_equiv), col[1]))

    # Format value line - colour code & shell beep alerts depending on case

        if args.b:
            if first_run:
                print(str.ljust("VALUE:", col[0]) + str.ljust(c_symb + str(value), col[1]))
            else:
                if threshold != 0:
                    if multiplier * curr_equiv > threshold:
                        print('\33[42m' + str.ljust("VALUE:", col[0]) +
                              str.ljust(c_symb + str(value), col[1]) + str.rjust(val_delta, col[2] +
                                                                                 col[3]) +
                              '\33[0m' + multi_bell)
                    elif value > best_value:
                        print('\33[7m' + str.ljust("VALUE:", col[0]) +
                              str.ljust(c_symb + str(value), col[1]) + str.rjust(val_delta, col[2] +
                                                                                 col[3]) +
                              '\33[0m')
                    else:
                        print(str.ljust("VALUE:", col[0]) + str.ljust(c_symb + str(value), col[1]) +
                              str.rjust(val_delta, col[2] + col[3]))
                else:
                    if value > best_value:
                        print('\33[7m' + str.ljust("VALUE:", col[0]) +
                              str.ljust(c_symb + str(value), col[1]) + str.rjust(val_delta, col[2] +
                                                                                 col[3]) +
                              '\33[0m')
                    else:
                        print(str.ljust("VALUE:", col[0]) + str.ljust(c_symb + str(value), col[1]) +
                              str.rjust(val_delta, col[2] + col[3]))

    # Format best-since-start line - the highest price * value in local currency during run time.
    # Alert if best increases

            if first_run:
                best_value = value
                print(str.ljust("BEST:", col[0]) + str.ljust(c_symb + str(best_value), col[1]) +
                      str.rjust("@ " + peak_val_time, col[2] + col[3] + col[4]))
            elif value > best_value:
                best_value = value
                peak_val_time = now
                print('\33[7m' + str.ljust("BEST:", col[0]) + str.ljust(c_symb + str(value), col[1])
                      + str.rjust("@ " + peak_val_time, col[2] + col[3] + col[4]) + '\33[0m' + bell)
            elif value == best_value:
                print('\33[7m' + str.ljust("BEST:", col[0]) + str.ljust(c_symb + str(value), col[1])
                      + str.rjust("@ " + peak_val_time, col[2] + col[3] + col[4]) + '\33[0m')
            else:
                print(str.ljust("BEST:", col[0]) + str.ljust(c_symb + str(best_value), col[1]) +
                      str.rjust("@ " + peak_val_time, col[2] + col[3] + col[4]))

    # For reference: CSV_HDR = "Status,StartTime,StartTimeEST,Date,Symbol,SymbolPrice,SymbolHigh,
    # SymbolHighTime,Currency,CurrencyValue,CurrencyLow,CurrencyLowTime,Value,BestValue,
    # BestValueTime"

        if out_file != "":
            csv_str = now + "," + est_time + "," + start_date + "," + symbol + "," \
                      + str(stock_price) + "," + str(best_price) + "," + peak_stk_time + "," \
                      + currency + "," + str(curr_val) + "," + str(low_fx) + "," + low_fx_time \
                      + "," + str(value) + "," + str(best_value) + "," + peak_val_time
            write_csv_file(first_run, csv_str, csv_file)

    # Generate countdown timer

        print()
        print_countdown(bell, refresh, sum(col))
        print(delimiter)
        print()
        first_run = False

        # Check hotkeys

        if keystroke.kbhit():
            key = keystroke.getch()
            if key in ["Q", "q"]:  # Quit
                print()
                print("Thanks for all the fish, smeg head.")
                print()
                quit_flag = True
            elif key in ["R", "r"]:  # Reset
                first_run = True
                start_date = datetime.now()
                start_date = start_date.strftime("%d-%m-%Y")
                start_time = datetime.now()
                start_time = start_time.strftime("%H:%M:%S")
                peak_val_time = start_time
                peak_stk_time = start_time
                low_fx_time = start_time
                start_time_est = datetime.now(timezone('America/New_York'))
                start_time_est = start_time_est.strftime("%H:%M:%S")
                val_delta = ""
                price_delta = ""
                fx_delta = ""
            elif key in ["U", "u"]:  # Up threshold
                threshold = threshold + thresh_change
                print("\33[44m" + str.center("--- Increase threshold to " + c_symb +
                                             str(round(threshold, 2)) + " ---", sum(col)) +
                      "\33[0m")
                print()
            elif key in ["D", "d"]:  # Down threshold
                if threshold - thresh_change <= 0:
                    threshold = 0.0
                else:
                    threshold = threshold - thresh_change
                print("\33[44m" + str.center("--- Reduce threshold to " + c_symb +
                                             str(round(threshold, 2)) + " ---", sum(col)) +
                      "\33[0m")
                print()
            elif key in ["F", "f"]:  # Faster iteration
                if refresh - refresh_inc <= 2:
                    refresh = refresh_inc
                else:
                    refresh = refresh - refresh_inc
            elif key in ["S", "s"]:  # Slower iteration
                refresh = refresh + refresh_inc
            elif key in ["T", "t"]:  # Print current threshold
                print("\33[44m" + str.center("--- Current threshold is " + c_symb +
                                             str(round(threshold, 2)) + " ---", sum(col)) +
                      "\33[0m")
                print()
            elif key in ["B", "b"]:  # Toggle bell
                if bell != DEF_BELL:
                    bell = DEF_BELL
                    multi_bell = DEF_MULTI_BELL
                    print("\33[44m" + str.center("--- Alerts enabled ---", sum(col)) + "\33[0m")
                    print()
                else:
                    bell = ""
                    multi_bell = ""
                    print("\33[44m" + str.center("--- Alerts disabled ---", sum(col)) + "\33[0m")
                    print()
            else:
                pass



    # Normal termination activities

    keystroke.set_normal_term()
    if out_file != "":
        csv_file.close()
    sys.exit(0)


if __name__ == '__main__':
    main()
