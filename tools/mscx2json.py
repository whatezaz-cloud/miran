"""Convert a MuseScore 4 .mscx (single staff) to Miran's score JSON.
Keeps: key/time signature, tempo, notes & chords, rests, dots, ties, tuplets,
explicit accidentals (incl. Arabic half-flat via tuning -50), repeats, voltas,
simile (measure-repeat) bars, segno markers."""
import sys, json, re, xml.etree.ElementTree as ET

DUR = {"whole": 1, "half": 2, "quarter": 4, "eighth": 8, "16th": 16, "32nd": 32, "64th": 64}
ACC = {"accidentalNatural": "n", "accidentalFlat": "b", "accidentalSharp": "#",
       "accidentalBakiyeFlat": "d", "accidentalMirroredFlat": "d", "accidentalQuarterToneFlatArabic": "d",
       "accidentalQuarterToneFlatStein": "d", "accidentalQuarterToneSharpStein": "+",
       "accidentalQuarterToneSharpArabic": "+", "accidentalDoubleFlat": "bb", "accidentalDoubleSharp": "##"}


def tpc_letter(tpc):
    letter = "FCGDAEB"[(tpc + 1) % 7]
    alter = (tpc + 1) // 7 - 2
    return letter, alter


def convert(path):
    root = ET.parse(path).getroot()
    score = root.find("Score")
    staff = None
    for st in score.findall("Staff"):
        if st.find("Measure") is not None:
            staff = st
            break
    title = ""
    for t in staff.iter("Text"):
        if (t.findtext("style") or "") == "title":
            title = "".join(t.find("text").itertext()).strip()
    out = {"key": 0, "ts": [4, 4], "tempo": 80, "measures": []}
    measures = staff.findall("Measure")
    for mi, m in enumerate(measures):
        md = {"events": []}
        if m.find("startRepeat") is not None:
            md["repStart"] = True
        er = m.findtext("endRepeat")
        if er:
            md["repEnd"] = int(er)
        for mk in m.iter("Marker"):
            md["marker"] = mk.findtext("label") or ""
        voice = m.find("voice")
        tup = None
        tup_id = 0
        for el in list(voice):
            tag = el.tag
            if tag == "KeySig":
                out["key"] = int(el.findtext("concertKey") or el.findtext("accidental") or 0)
            elif tag == "TimeSig":
                out["ts"] = [int(el.findtext("sigN")), int(el.findtext("sigD"))]
            elif tag == "Tempo":
                out["tempo"] = round(float(el.findtext("tempo")) * 60)
            elif tag == "Spanner" and el.get("type") == "Volta" and el.find("Volta") is not None:
                v = el.find("Volta")
                n = el.find("next/location/measures")
                md["volta"] = {"endings": [int(x) for x in (v.findtext("endings") or "1").split(",")],
                               "text": v.findtext("beginText") or "", "len": int(n.text) if n is not None else 1}
            elif tag == "Tuplet":
                tup_id += 1
                tup = {"id": tup_id, "actual": int(el.findtext("actualNotes")), "normal": int(el.findtext("normalNotes"))}
            elif tag == "endTuplet":
                tup = None
            elif tag == "MeasureRepeat":
                md["simile"] = True
            elif tag in ("Chord", "Rest"):
                dt = el.findtext("durationType")
                ev = {"dots": int(el.findtext("dots") or 0)}
                if tup:
                    ev["tup"] = dict(tup)
                if dt == "measure":
                    ev.update({"type": "rest", "full": True})
                    md["events"].append(ev)
                    continue
                ev["dur"] = DUR[dt]
                if tag == "Rest":
                    ev["type"] = "rest"
                else:
                    ev["type"] = "chord"
                    notes = []
                    for nt in el.findall("Note"):
                        pitch = int(nt.findtext("pitch"))
                        tpc = int(nt.findtext("tpc"))
                        tuning = float(nt.findtext("tuning") or 0)
                        letter, alter = tpc_letter(tpc)
                        octv = (pitch - alter) // 12 - 1
                        n = {"L": letter, "oct": octv, "p": round(pitch + tuning / 100, 2)}
                        a = nt.find("Accidental/subtype")
                        if a is not None:
                            n["acc"] = ACC.get(a.text, "n")
                        for sp in nt.findall("Spanner"):
                            if sp.get("type") == "Tie":
                                if sp.find("next") is not None:
                                    n["tieS"] = True
                                if sp.find("prev") is not None:
                                    n["tieE"] = True
                        notes.append(n)
                    ev["notes"] = notes
                md["events"].append(ev)
        out["measures"].append(md)
    # simile bars: copy previous bar's content (keep the flag for display)
    for i, md in enumerate(out["measures"]):
        if md.get("simile") and i > 0:
            src = out["measures"][i - 1]
            md["events"] = json.loads(json.dumps(src["events"]))
    return title, out


if __name__ == "__main__":
    title, sc = convert(sys.argv[1])
    print(json.dumps({"title": title, "score": sc}, ensure_ascii=False))
