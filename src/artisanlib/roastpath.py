#!/usr/bin/env python3

# ABOUT
# RoastPATH HTML Roast Profile importer for Artisan

import time as libtime
import dateutil
from datetime import datetime
import requests
from requests_file import FileAdapter
import re
import json
from lxml import html

from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QApplication

from artisanlib.util import encodeLocal

# returns a dict containing all profile information contained in the given RoastPATH document pointed by the given QUrl
def extractProfileRoastPathHTML(url):
    res = {} # the interpreted data set
    try:
        s = requests.Session()
        s.mount('file://', FileAdapter())
        page = s.get(url.toString())
        tree = html.fromstring(page.content)
        
        title = ""
        date = tree.xpath('//div[contains(@class, "roast-top")]/*/*[local-name() = "h5"]/text()')
        if date and len(date) > 0:
            date_str = date[0].strip().split()
            if len(date_str) > 2:
                dateQt = QDateTime.fromString(date_str[-2]+date_str[-1], "yyyy-MM-ddhh:mm")
                if dateQt.isValid():
                    res["roastdate"] = encodeLocal(dateQt.date().toString())
                    res["roastisodate"] = encodeLocal(dateQt.date().toString(Qt.ISODate))
                    res["roasttime"] = encodeLocal(dateQt.time().toString())
                    res["roastepoch"] = int(dateQt.toTime_t())
                    res["roasttzoffset"] = libtime.timezone
                title = "".join(date_str[:-2]).strip()
                if len(title)>0 and title[-1] == "-": # we remove a trailing -
                    title = title[:-1].strip()
            elif len(date_str)>0:
                title = "".join(date_str)

        coffee = ""
        for m in ["Roasted By","Coffee","Batch Size","Notes","Organization"]:
            s = '//*[@class="ml-2" and normalize-space(text())="Details"]/following::table[1]/tbody/tr[*]/td/*[normalize-space(text())="{}"]/following::td[1]/text()'.format(m)
            value = tree.xpath(s)
            if len(value) > 0:
                meta = value[0].strip()
                try:
                    if m == "Roasted By":
                        res["operator"] = meta
                    elif m == "Coffee":
                        coffee = meta
                        if title == "" or title == "Roast":
                            res["title"] = coffee
                    elif m == "Notes":
                        res["roastingnotes"] = meta
                    elif m == "Batch Size":
                        v,u = meta.split()
                        res["weight"] = [float(v),0,("Kg" if u.strip() == "kg" else "lb")]
                    elif m == "Organization":
                        res["organization"] = meta
                except:
                    pass
        
        beans = ""
        for m in ["Nickname","Country","Region","Farm","Varietal","Process"]:
            s = '//*[@class="ml-2" and normalize-space(text())="Greens"]/following::table[1]/tbody/tr/td[count(//table/thead/tr/th[normalize-space(text())="{}"]/preceding-sibling::th)+1]/text()'.format(m)
            value = tree.xpath(s)
            if len(value)>0:
                meta = value[0].strip()
                if meta != "":
                    if beans == "":
                        beans = meta
                    else:
                        beans += ", " + meta
        if coffee != "" and title in res: # we did not use the "coffee" as title
            if beans == "": 
                beans = coffee
            else:
                beans = coffee + "\n" + beans
        if beans != "":
            res["beans"] = beans
        if not "title" in res and title != "":
            res["title"] = title
        
        data = {}
        for e in ["btData", "etData", "atData", "eventData", "rorData", "noteData"]:
            d = re.findall("var {} = JSON\.parse\('(.+?)'\);".format(e), page.content.decode("utf-8"), re.S)
            bt = []
            if d:
                data[e] = json.loads(d[0])
        
        if "btData" in data and len(data["btData"]) > 0 and "Timestamp" in data["btData"][0]:
            # BT
            bt = data["btData"]
            baseTime = dateutil.parser.parse(bt[0]["Timestamp"]).timestamp()
            res["mode"] = 'C'
            res["timex"] = [dateutil.parser.parse(d["Timestamp"]).timestamp() - baseTime for d in bt]
            res["temp2"] = [d["StandardValue"] for d in bt]
        
            # ET
            if "etData" in data and len(data["btData"]) == len(data["etData"]):
                et = data["etData"]
                res["temp1"] = [d["StandardValue"] for d in et]
            else:
                res["temp1"] = [-1]*len(res["temp2"])
            
            # Events
            timeindex = [-1,0,0,0,0,0,0,0]
            if "eventData" in data:
                marks = {
                    "Charge" : 0,
                    "Green > Yellow" : 1,
                    "First Crack" : 2,
                    "Second Crack" : 4,
                    "Drop" : 6}
                for d in data["eventData"]:
                    if "EventName" in d and d["EventName"] in marks and "Timestamp" in d:
                        tx = dateutil.parser.parse(d["Timestamp"]).timestamp() - baseTime
                        try:
#                            tx_idx = res["timex"].index(tx) # does not cope with dropouts as the next line:
                            tx_idx = next(i for i,item in enumerate(res["timex"]) if item >= tx)
                            timeindex[marks[d["EventName"]]] = tx_idx
                        except:
                            pass
            res["timeindex"] = timeindex
            
            # Notes
            if "noteData" in data:
                specialevents = []
                specialeventstype = []
                specialeventsvalue = []
                specialeventsStrings = []
                noteData = data["noteData"]
                for n in noteData:
                    if "Timestamp" in n and "NoteTypeId" in n and "Note" in n:
                        c = dateutil.parser.parse(n["Timestamp"]).timestamp() - baseTime
                        try:
                            timex_idx = res["timex"].index(c)
                            specialevents.append(timex_idx)
                            note_type = n["NoteTypeId"]
                            if note_type == 0: # Fuel
                                specialeventstype.append(3)
                            elif note_type == 1: # Fan
                                specialeventstype.append(0)
                            elif note_type == 2: # Drum
                                specialeventstype.append(1)
                            else: # n == 3: # Notes
                                specialeventstype.append(4)
                            try:
                                v = float(n["Note"])
                                v = v/10. + 1
                                specialeventsvalue.append(v)
                            except:
                                specialeventsvalue.append(0)
                            specialeventsStrings.append(n["Note"])
                        except:
                            pass
                if len(specialevents) > 0:
                    res["specialevents"] = specialevents
                    res["specialeventstype"] = specialeventstype
                    res["specialeventsvalue"] = specialeventsvalue
                    res["specialeventsStrings"] = specialeventsStrings

            if "atData" in data or "rorData" in data:
                res["extradevices"] = []
                res["extratimex"] = []
                res["extratemp1"] = []
                res["extratemp2"] = []
                res["extraname1"] = []
                res["extraname2"] = []
                res["extramathexpression1"] = []
                res["extramathexpression2"] = []
                res["extraLCDvisibility1"] = []
                res["extraLCDvisibility2"] = []
                res["extraCurveVisibility1"] = []
                res["extraCurveVisibility2"] = []
                res["extraDelta1"] = []
                res["extraDelta2"] = []
                res["extraFill1"] = []
                res["extraFill2"] = []
                res["extradevicecolor1"] = []
                res["extradevicecolor2"] = []
                res["extramarkersizes1"] = []
                res["extramarkersizes2"] = []
                res["extramarkers1"] = []
                res["extramarkers2"] = []
                res["extralinewidths1"] = []
                res["extralinewidths2"] = []
                res["extralinestyles1"] = []
                res["extralinestyles2"] = []
                res["extradrawstyles1"] = []
                res["extradrawstyles2"] = []

                # AT
                if "atData" in data:
                    res["extradevices"].append(25)
                    res["extraname1"].append("AT")
                    res["extraname2"].append("")
                    res["extramathexpression1"].append("")
                    res["extramathexpression2"].append("")
                    res["extraLCDvisibility1"].append(True)
                    res["extraLCDvisibility2"].append(False)
                    res["extraCurveVisibility1"].append(True)
                    res["extraCurveVisibility2"].append(False)
                    res["extraDelta1"].append(False)
                    res["extraDelta2"].append(False)
                    res["extraFill1"].append(False)
                    res["extraFill2"].append(False)
                    res["extradevicecolor1"].append('black')
                    res["extradevicecolor2"].append('black')
                    res["extramarkersizes1"].append(6.0)
                    res["extramarkersizes2"].append(6.0)
                    res["extramarkers1"].append(None)
                    res["extramarkers2"].append(None)
                    res["extralinewidths1"].append(1.0)
                    res["extralinewidths2"].append(1.0)
                    res["extralinestyles1"].append('-')
                    res["extralinestyles2"].append('-')
                    res["extradrawstyles1"].append('default')
                    res["extradrawstyles2"].append('default')
                    at = data["atData"]
                    timex = [dateutil.parser.parse(d["Timestamp"]).timestamp() - baseTime for d in at]
                    res["extratimex"].append(timex)
                    res["extratemp1"].append([d["StandardValue"] for d in at])
                    res["extratemp2"].append([-1]*len(timex))
                
                # BT RoR
                if "rorData" in data:
                    res["extradevices"].append(25)
                    res["extraname1"].append("RoR")
                    res["extraname2"].append("")
                    res["extramathexpression1"].append("")
                    res["extramathexpression2"].append("")
                    res["extraLCDvisibility1"].append(True)
                    res["extraLCDvisibility2"].append(False)
                    res["extraCurveVisibility1"].append(False)
                    res["extraCurveVisibility2"].append(False)
                    res["extraDelta1"].append(True)
                    res["extraDelta2"].append(False)
                    res["extraFill1"].append(False)
                    res["extraFill2"].append(False)
                    res["extradevicecolor1"].append('black')
                    res["extradevicecolor2"].append('black')
                    res["extramarkersizes1"].append(6.0)
                    res["extramarkersizes2"].append(6.0)
                    res["extramarkers1"].append(None)
                    res["extramarkers2"].append(None)
                    res["extralinewidths1"].append(1.0)
                    res["extralinewidths2"].append(1.0)
                    res["extralinestyles1"].append('-')
                    res["extralinestyles2"].append('-')
                    res["extradrawstyles1"].append('default')
                    res["extradrawstyles2"].append('default')
                    ror = data["rorData"]
                    timex = [dateutil.parser.parse(d["Timestamp"]).timestamp() - baseTime for d in ror]
                    res["extratimex"].append(timex)
                    res["extratemp1"].append([d["StandardValue"] for d in ror])
                    res["extratemp2"].append([-1]*len(timex))

    except Exception as e:
#        import traceback
#        import sys
#        traceback.print_exc(file=sys.stdout)
        pass
    return res