2026-01-01 10:00:00 step: n=1 name=Intake rev=0 session=sess1111-aaaa model=gpt-x
2026-01-01 10:00:01 ask: gate=G1a q="start" rec="Yes" session=sess1111-aaaa
2026-01-01 10:00:02 answer: gate=G1a choice="Yes" session=sess1111-aaaa
2026-01-01 10:01:00 step: n=3 name=Plan rev=0 session=sess1111-aaaa model=gpt-x
2026-01-01 10:02:00 step: n=5 name=Execute rev=0 session=sess1111-aaaa model=gpt-x
2026-01-01 10:02:05 call: agent=my_agent_coder model=- effort=- isolation=- background=false
2026-01-01 10:02:06 start: agent=my_agent_coder id=sess2222-bbbb configured=- effort=- session=sess1111-aaaa
2026-01-01 10:02:30 guard: hook=scope-guard agent=my_agent_coder id=sess2222-bbbb tool=Bash decision=deny why="outside scope" cwd=/tmp/x
2026-01-01 10:03:00 stop: id=sess2222-bbbb actual=gpt-x tokens=10 in=5 out=5 cw=0 cr=0 secs=54 result="DONE" end=ok mode=auto effort=-
