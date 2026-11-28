"""Generate a single SVG from the public GitHub profile and repository data."""
import calendar
import json
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

USER = os.environ.get('GITHUB_USERNAME', 'Xam-585')
TOKEN = os.environ.get('GH_TOKEN', '')
OUTPUT = Path(__file__).resolve().parents[1] / 'assets' / 'dashboard.svg'
PALETTE = ['#242424', '#480808', '#790808', '#b80000', '#ff3333']
COLORS = {'HTML':'#e34c26', 'CSS':'#563d7c', 'JavaScript':'#f1e05a',
          'TypeScript':'#3178c6', 'Python':'#3572a5', 'C':'#888888',
          'C++':'#f34b7d', 'Assembly':'#b07219', 'Java':'#b07219',
          'Shell':'#89e051', 'Rust':'#dea584', 'Other':'#777777'}


def request(url, api=False):
    headers = {'User-Agent':'profile-dashboard', 'Accept-Language':'en-US',
               'Accept':'application/vnd.github+json' if api else 'text/html'}
    if api and TOKEN:
        headers['Authorization'] = 'Bearer ' + TOKEN
    try:
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            body = response.read().decode('utf-8')
    except HTTPError as error:
        # The Actions token may not have access to other repositories.
        if not (api and TOKEN and error.code in (401, 403, 404)):
            raise
        headers.pop('Authorization', None)
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            body = response.read().decode('utf-8')
    return json.loads(body) if api else body


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells, self.tips = {}, {}
        self.current, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'td' and a.get('data-date'):
            self.cells[a['data-date']] = (a.get('id'), a.get('data-count'))
        if tag == 'tool-tip' and a.get('for'):
            self.current, self.parts = a['for'], []

    def handle_data(self, data):
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'tool-tip' and self.current is not None:
            self.tips[self.current] = ''.join(self.parts)
            self.current = None

    def counts(self):
        result = {}
        for day, (ident, raw) in self.cells.items():
            if raw is not None and raw.isdecimal():
                result[date.fromisoformat(day)] = int(raw)
                continue
            match = re.search(r'\b(No|[0-9][0-9,]*)\s+contributions?\b',
                              self.tips.get(ident, ''), re.I)
            if match:
                value = match.group(1)
                result[date.fromisoformat(day)] = 0 if value.lower() == 'no' else int(value.replace(',', ''))
        return result


def get_contributions(start, end):
    base = 'https://github.com/users/' + quote(USER, safe='') + '/contributions'
    result = {}
    # Default profile calendar is a rolling year. Explicit year ranges fill any gaps.
    urls = [base] + [base + '?' + urlencode({'from':date(y,1,1).isoformat(),
             'to':min(end,date(y,12,31)).isoformat()}) for y in range(start.year,end.year+1)]
    days = [start + timedelta(days=i) for i in range((end-start).days+1)]
    for url in urls:
        parser = CalendarParser()
        parser.feed(request(url))
        result.update(parser.counts())
        if all(day in result for day in days):
            return {day:result[day] for day in days}
    missing = sum(day not in result for day in days)
    raise RuntimeError(f'Public calendar incomplete ({missing} days missing); refusing to invent data.')


def get_languages():
    totals = Counter()
    page = 1
    while True:
        repos = request('https://api.github.com/users/' + quote(USER,safe='') +
                        '/repos?type=owner&per_page=100&page=' + str(page), api=True)
        for repo in repos:
            if not repo['fork'] and not repo['private'] and repo['size'] > 0:
                totals.update(request(repo['languages_url'], api=True))
        if len(repos) < 100:
            break
        page += 1
    ranked = totals.most_common()
    return ranked[:5] + [('Other',sum(n for _,n in ranked[5:]))] if len(ranked)>5 else ranked


def render(counts, languages):
    end, start = max(counts), min(counts)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="440" viewBox="0 0 900 440" role="img" aria-labelledby="title desc">',
           '<title id="title">GitHub Development Dashboard</title>',
           '<desc id="desc">Public contributions over the last 365 and 31 days, and public repository languages by bytes.</desc>',
           '<defs><linearGradient id="accent"><stop stop-color="#000000"/><stop offset="60%" stop-color="#630606"/><stop offset="100%" stop-color="#b80000"/></linearGradient></defs>',
           '<rect width="900" height="440" fill="#000000"/>',
           '<rect width="900" height="4" fill="url(#accent)"/>',
           '<rect y="436" width="900" height="4" fill="url(#accent)"/>']
    def text(x,y,value,size=12,color='#c9d1d9',anchor='start',bold=False):
        out.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-family="Arial, Helvetica, sans-serif" font-weight="{600 if bold else 400}" text-anchor="{anchor}">{escape(str(value))}</text>')
    def rect(x,y,w,h,color,rx=0):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{color}"/>')
    def line(x1,y1,x2,y2,color='#282828',dash=''):
        extra = f' stroke-dasharray="{dash}"' if dash else ''
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"{extra}/>')
    def heading(x,y,value):
        text(x,y,value,17,'#ff3333',bold=True)
    heading(26,34,'Development Heatmap')
    text(26,51,f'Last 365 days  |  {sum(counts.values()):,} contributions',11,'#a1a1aa')
    sunday = start - timedelta(days=(start.weekday()+1)%7)
    last_label_col = -10
    for day,count in sorted(counts.items()):
        col,row = divmod((day-sunday).days,7)
        x,y = 38+col*9.5,74+row*10
        # Fixed intensity bands make the same count the same color every day.
        level = 0 if count==0 else 1 if count<=2 else 2 if count<=5 else 3 if count<=9 else 4
        out.append(f'<rect x="{x}" y="{y}" width="8" height="8" rx="1" fill="{PALETTE[level]}"><title>{day}: {count} contributions</title></rect>')
        if (day.day==1 or day==start) and col-last_label_col>=3:
            text(x,68,calendar.month_abbr[day.month],9,'#a1a1aa')
            last_label_col=col
    for row,label in [(1,'M'),(3,'W'),(5,'F')]:
        text(26,81+row*10,label,9,'#a1a1aa')
    text(38,160,'Less',10,'#a1a1aa')
    for i,color in enumerate(PALETTE):
        rect(68+i*12,151,9,9,color,1)
    text(132,160,'More',10,'#a1a1aa')
    line(566,22,566,173)
    heading(586,34,'Most Used Languages')
    text(586,51,'Public repositories · code by bytes',11,'#a1a1aa')
    total = sum(n for _,n in languages)
    x = 586
    if not total:
        text(586,90,'No language data available',12)
    for i,(name,n) in enumerate(languages):
        if not total:
            break
        width = 286*n/total
        color = COLORS.get(name,'#a0a0a0')
        rect(round(x,2),62,round(width,2),7,color)
        x += width
        y = 88+i*15
        rect(586,y-8,7,7,color,2)
        text(600,y,name if len(name)<=30 else name[:27]+'...',11)
        text(872,y,f'{100*n/total:.1f}%',11,anchor='end')
    line(26,186,874,186)
    heading(26,216,'Daily Contribution Activity')
    text(874,216,'Last 31 days',11,'#a1a1aa',anchor='end')
    recent = sorted(counts.items())[-31:]
    ymax = max(4, math.ceil(max(n for _,n in recent)/4)*4)
    left,right,top,bottom = 54,872,239,391
    points=[]
    for i in range(5):
        value=ymax*i//4
        y=bottom-(bottom-top)*i/4
        line(left,y,right,y,'#292929','3 4')
        text(left-9,y+4,value,10,'#a1a1aa','end')
    for i,(day,n) in enumerate(recent):
        x=left+(right-left)*i/max(1,len(recent)-1)
        y=bottom-(bottom-top)*n/ymax
        points.append((x,y))
        line(x,top,x,bottom,'#171717','2 4')
        if i%5==0:
            text(x,409,day.strftime('%d %b'),10,'#a1a1aa','middle')
    coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
    out.append(f'<polygon points="{left},{bottom} {coords} {points[-1][0]},{bottom}" fill="#b80000" opacity="0.19"/>')
    out.append(f'<polyline points="{coords}" fill="none" stroke="#e00000" stroke-width="2.5" stroke-linejoin="round"/>')
    for (x,y),(day,n) in zip(points,recent):
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#ff3333"><title>{day}: {n} contributions</title></circle>')
    text(26,426,'GitHub profile contributions',9,'#777777')
    text(874,426,f'Through {end.isoformat()} (UTC)',9,'#777777','end')
    out.append('</svg>')
    return '\n'.join(out)+'\n'


def main():
    end = datetime.now(timezone.utc).date()
    counts = get_contributions(end-timedelta(days=364),end)
    svg = render(counts,get_languages())
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(svg,encoding='utf-8')
    print(f'Generated {OUTPUT.name} for {USER}')


if __name__ == '__main__':
    main()
