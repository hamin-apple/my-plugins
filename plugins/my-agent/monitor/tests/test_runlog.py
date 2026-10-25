import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from monitor.runlog import parse_line, read_lines


class ParseLineTest(unittest.TestCase):
    def test_parses_kv_and_quotes(self):
        line = parse_line('2026-10-24 16:01:15 ask: gate=G2 tool=Bash q="npm i x"')
        self.assertEqual(line.kind, 'ask')
        self.assertEqual(line.ts, datetime(2026, 10, 24, 16, 1, 15))
        self.assertEqual(line.f, {'gate': 'G2', 'tool': 'Bash', 'q': 'npm i x'})

    def test_unknown_kind_kept(self):
        line = parse_line('2026-10-24 16:01:15 foo: a=1')
        self.assertEqual(line.kind, 'foo')

    def test_bare_kind_without_fields(self):
        line = parse_line('2026-10-24 16:01:15 abort:')
        self.assertEqual((line.kind, line.f), ('abort', {}))

    def test_garbage_returns_none(self):
        for text in ['hello', '', '2026-10-24 16:01 ask', '# run-log 261024-x']:
            self.assertIsNone(parse_line(text), text)

    def test_unclosed_quote_returns_none(self):
        self.assertIsNone(parse_line('2026-10-24 16:01:15 ask: q="npm i'))


class ReadLinesTest(unittest.TestCase):
    def test_read_lines_skips_partial_last_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'run-log.md'
            p.write_text('# run-log x\n2026-10-24 15:30:00 step: n=1 name=Intake rev=0 session=s\n'
                         '2026-10-24 15:31:00 call: agent=my-agent:explorer', encoding='utf-8')
            lines = read_lines(p)
            self.assertEqual([l.kind for l in lines], ['step'])

    def test_missing_file_is_empty(self):
        self.assertEqual(read_lines(Path('/nonexistent/run-log.md')), [])


if __name__ == '__main__':
    unittest.main()
