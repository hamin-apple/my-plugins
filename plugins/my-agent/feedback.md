# my-agent feedback

회고에서 나온 개선점입니다(설계 문서 4.11절). 한 줄에 하나씩, 레벨과 상태를 붙입니다. 한 레벨에 `open`이 4개 이상이면 그 레벨을 정리할 때입니다.

형식: `- [open|done] L<1-4> <YYYY-MM-DD> <task-id>: <개선점>` (done이면 끝에 `→ <고친 내용>`)

## Open

- [open] L2 2026-10-25 261025-meeting-notes-template: architect가 writer의 쓰기 범위(work/, prototype/ 뿐)를 모르고 작업 단위의 고칠 파일을 templates/로 적어 writer가 PARTIAL로 끝남. architect 지침에 writer 결과는 work/에 쓰고 저장은 Deliver에서 한다고 명시
- [open] L2 2026-10-25 261025-meeting-notes-template: reviewer가 review.md를 쓰지 못해 L1이 보고를 대신 저장함. reviewer의 쓰기 권한과 시스템 규칙이 충돌하는지 확인
- [open] L4 2026-10-25 261025-meeting-notes-template: G1b 승인 전 hook이 .active 작성 뒤 projects.txt 등록과 date 치환이 든 복합 명령을 막음. Intake 7번의 쓰기 대상을 hook 허용 목록에 넣거나 순서를 조정
- [open] L4 2026-10-25 261025-python-shlex-note: scope-guard가 architect의 프로파일·phase 규칙 파일(research.md, plan.md) 읽기를 막아, architect가 규칙을 읽지 못하고 L1이 준 기준만으로 계획을 씀. 읽기 허용 목록에 규칙 파일 추가 검토
- [open] L1 2026-10-25 261025-python-shlex-note: scope.md 결과물 형식의 저장 경로 표기 작업 폴더의 deliverable/ 가 모호해 Plan Review에서 BLOCKER가 됨. research 프로파일 Scope 인터뷰에서 작업 폴더 기준 전체 경로를 쓰도록 명시
- [open] L4 2026-10-25 261025-wc-lines-option: G1b 승인 전 hook이 date 치환이 든 승인 줄 쓰기 명령을 막음. build/plan phase 문서가 Edit 도구로 쓰라고 안내하거나 hook이 승인 줄 쓰기를 허용해야 함
- [open] L1 2026-10-25 261025-wc-lines-option: 메인 세션 실제 모델이 설정(opus)과 달라 단계마다 MISMATCH가 반복됨. 세션 시작 때 한 번만 알리면 충분
- [open] L4 2026-10-25 261025-upper-rev-tools: verdict 점검 hook이 G3 이전(Execute·Merge)에도 $( 가 든 복합 Bash 명령을 'verify.md 첫 줄이 ALL PASS가 아닙니다' 메시지로 막음. 명령을 나누면 통과해서 오탐으로 보임. G3 단계(git commit)에만 적용되도록 범위를 좁힐 것
- [open] L2 2026-10-25 261025-upper-rev-tools: dev 프로파일 architect가 추적 중인 pyc의 M 상태를 이유로 병렬 그룹을 막았음. pyc 같은 부산물 변경과 실제 미커밋 작업 변경을 구분하거나, 계획 전에 git status 정리 여부를 L1이 확인해 넘길 것
- [open] L4 2026-10-25 261025-upper-rev-tools: SendMessage로 이어 부른 architect(abc16c02f783e90be)의 두 번째, 세 번째 실행은 run-log에 start만 있고 stop 줄(토큰, 결과)이 남지 않음. 재개된 서브에이전트의 stop도 기록할 것
- [open] L1 2026-10-25 261025-textstats-module: run-log이 매 줄 MISMATCH를 냄: 세션 설정은 opus인데 실제 모델은 claude-sonnet-5-5로 기록됨. 세션 모델 설정과 skill의 모델 기대값을 맞추거나 MISMATCH를 한 번만 알리도록 정리 필요

## Done
