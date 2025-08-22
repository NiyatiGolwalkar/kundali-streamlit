
import os, datetime, requests, pytz
import streamlit as st
import pandas as pd
import swisseph as swe
from timezonefinder import TimezoneFinder
from math import floor
from docx import Document
from io import BytesIO

st.set_page_config(page_title="Kundali – Hindi KP (Fixed)", layout="wide", page_icon="🪔")

HN = {'Su':'सूर्य','Mo':'चंद्र','Ma':'मंगल','Me':'बुध','Ju':'गुरु','Ve':'शुक्र','Sa':'शनि','Ra':'राहु','Ke':'केतु'}
ORDER = ['Ke','Ve','Su','Mo','Ma','Ra','Ju','Sa','Me']
YEARS = {'Ke':7,'Ve':20,'Su':6,'Mo':10,'Ma':7,'Ra':18,'Ju':16,'Sa':19,'Me':17}
NAK = 360.0/27.0

def set_sidereal(): swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)

def dms(deg): d=int(deg); m=int((deg-d)*60); s=int(round((deg-d-m/60)*3600)); return d,m,s
def fmt_deg_sign(lon_sid):
    sign=int(lon_sid//30); deg=lon_sid - sign*30; d,m,s=dms(deg); return f"{d:02d}°{m:02d}'{s:02d}\"", (sign+1)

def kp_sublord(lon_sid):
    part = lon_sid % 360.0
    ni = int(part // NAK); pos = part - ni*NAK
    lord = ORDER[ni % 9]
    start = ORDER.index(lord)
    seq = [ORDER[(start+i)%9] for i in range(9)]
    acc = 0.0
    for L in seq:
        seg = NAK * (YEARS[L]/120.0)
        if pos <= acc + seg + 1e-9: return lord, L
        acc += seg
    return lord, seq[-1]

def geocode(place, api_key):
    if not api_key: raise RuntimeError("Geoapify key missing. Add GEOAPIFY_API_KEY in Secrets.")
    url="https://api.geoapify.com/v1/geocode/search"
    r=requests.get(url, params={"text":place, "format":"json", "limit":1, "apiKey":api_key}, timeout=12)
    j=r.json()
    if r.status_code!=200: raise RuntimeError(f"Geoapify {r.status_code}: {j.get('message', str(j)[:150])}")
    if j.get("results"):
        res=j["results"][0]; return float(res["lat"]), float(res["lon"]), res.get("formatted", place)
    if j.get("features"):
        lon,lat=j["features"][0]["geometry"]["coordinates"]; return float(lat), float(lon), place
    raise RuntimeError("Place not found.")

def tz_from_latlon(lat, lon, dt_local):
    tf = TimezoneFinder(); tzname = tf.timezone_at(lat=lat, lng=lon) or "Etc/UTC"
    tz = pytz.timezone(tzname); dt_local_aware = tz.localize(dt_local)
    dt_utc_naive = dt_local_aware.astimezone(pytz.utc).replace(tzinfo=None)
    offset_hours = tz.utcoffset(dt_local_aware).total_seconds()/3600.0
    return tzname, offset_hours, dt_utc_naive

def sidereal_positions(dt_utc):
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour + dt_utc.minute/60 + dt_utc.second/3600)
    set_sidereal(); ay = swe.get_ayanamsa_ut(jd); flags=swe.FLG_MOSEPH
    out = {}
    for code, p in [('Su',swe.SUN),('Mo',swe.MOON),('Ma',swe.MARS),('Me',swe.MERCURY),
                    ('Ju',swe.JUPITER),('Ve',swe.VENUS),('Sa',swe.SATURN),('Ra',swe.MEAN_NODE)]:
        xx,_ = swe.calc_ut(jd, p, flags)   # <-- correct usage
        out[code] = (xx[0] - ay) % 360.0
    out['Ke'] = (out['Ra'] + 180.0) % 360.0
    return jd, ay, out

def positions_table(sidelons):
    rows=[]
    for code in ['Su','Mo','Ma','Me','Ju','Ve','Sa','Ra','Ke']:
        lon=sidelons[code]; deg,sign=fmt_deg_sign(lon); lord,sub=kp_sublord(lon)
        rows.append([HN[code], deg, sign, HN[lord], HN[sub]])
    return pd.DataFrame(rows, columns=["Planet","Degree","Sign","Lord","Sub-Lord"])

def main():
    st.title("Kundali — Hindi KP (Fixed)")

    c1,c2 = st.columns([1,1])
    with c1:
        name = st.text_input("Name")
        dob = st.date_input("Date of Birth", min_value=datetime.date(1900,1,1), max_value=datetime.date.today())
        tob = st.time_input("Time of Birth", step=datetime.timedelta(minutes=1))  # minute precision
    with c2:
        place = st.text_input("Place of Birth (City, State, Country)")
        tz_override = st.text_input("UTC offset override (optional, e.g., 5.5)", "")
    api_key = st.secrets.get("GEOAPIFY_API_KEY","")

    if st.button("Generate Horoscope"):
        try:
            lat, lon, disp = geocode(place, api_key)
            dt_local = datetime.datetime.combine(dob, tob)
            if tz_override.strip():
                tz_hours = float(tz_override); dt_utc = dt_local - datetime.timedelta(hours=tz_hours); tzname=f"UTC{tz_hours:+.2f} (manual)"
            else:
                tzname, tz_hours, dt_utc = tz_from_latlon(lat, lon, dt_local)
            st.info(f"Resolved {disp} → lat {lat:.6f}, lon {lon:.6f}, tz {tzname} (UTC{tz_hours:+.2f})")

            _, _, sidelons = sidereal_positions(dt_utc)
            df = positions_table(sidelons)
            st.subheader("Planetary Positions (Lord & Sub-Lord)"); st.dataframe(df)

            # simple docx
            doc = Document(); doc.add_heading(f"Kundali — {name}", 0)
            p = doc.add_paragraph(f"DOB: {dob}, TOB: {tob}, Place: {disp} (UTC{tz_hours:+.2f})")
            t = doc.add_table(rows=1, cols=len(df.columns)); hdr=t.rows[0].cells
            for i,c in enumerate(df.columns): hdr[i].text=c
            for _,row in df.iterrows():
                r=t.add_row().cells
                for i,c in enumerate(row): r[i].text=str(c)
            bio = BytesIO(); doc.save(bio)
            st.download_button("⬇️ Download DOCX", bio.getvalue(), file_name="kundali.docx")
        except Exception as e:
            st.error(str(e))

if __name__=='__main__':
    main()
