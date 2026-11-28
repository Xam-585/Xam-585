import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_dashboard as d

class DashboardTests(unittest.TestCase):
    def test_calendar_parser(self):
        p=d.CalendarParser()
        p.feed('''<td id="a" data-date="2026-11-27" data-level="0"></td>
        <tool-tip for="a">No contributions on November 27th.</tool-tip>
        <td id="b" data-date="2026-11-28"></td><tool-tip for="b">1,024 contributions on November 28th.</tool-tip>''')
        self.assertEqual(p.counts(),{date(2026,11,27):0,date(2026,11,28):1024})
    def test_missing_data_fails(self):
        with patch.object(d,'request',return_value='<html></html>'):
            with self.assertRaises(RuntimeError):
                d.get_contributions(date(2026,11,27),date(2026,11,28))
    def test_render(self):
        counts={date(2025,11,29)+timedelta(days=i):i%17 for i in range(365)}
        root=ET.fromstring(d.render(counts,[('C',100),('Python',200),('A&B',20)]))
        ns={'s':'http://www.w3.org/2000/svg'}
        self.assertEqual(len(root.findall('s:circle',ns)),31)
        self.assertEqual(len(root.findall('s:rect/s:title',ns)),365)
        self.assertIn('A&B',[node.text for node in root.findall('s:text',ns)])
    def test_zero_activity(self):
        counts={date(2025,11,29)+timedelta(days=i):0 for i in range(365)}
        self.assertIn('No language data',d.render(counts,[]))
    def test_language_aggregation(self):
        repos=[{'fork':False,'private':False,'size':1,'languages_url':'https://api.github.com/one'},
               {'fork':True,'private':False,'size':1,'languages_url':'https://api.github.com/fork'}]
        with patch.object(d,'request',side_effect=[repos,{'Python':100,'C':20}]):
            self.assertEqual(d.get_languages(),[('Python',100),('C',20)])

if __name__=='__main__': unittest.main()
