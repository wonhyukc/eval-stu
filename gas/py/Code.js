/**
 * 파이썬 4반 성적 시트 정렬 메뉴
 * score 탭을 주차 역순 → 학번 오름차순으로 정렬하고 No를 재부여합니다.
 */

const SCORE_TAB_NAME = "score";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("관리자 설정")
    .addItem("🔄 score 탭 정렬 (주차↓ 학번↑)", "sortScoreTab")
    .addSeparator()
    .addItem("🔒 progress 1-4행 + 고정열 보호 설정", "protectProgressTab")
    .addToUi();
}

/**
 * progress 탭 표준 보호 설정 (파이썬 4반)
 * - 1-4행 (mean, stdev, count, 헤더): 보호
 * - A-P열 (학번, 이름, 진도 수식열): 보호
 * - Q열(한타04) 이후 학생 입력 영역: 편집 허용
 */
function protectProgressTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const me = Session.getEffectiveUser();
  const sheet = ss.getSheetByName("progress");

  if (!sheet) {
    SpreadsheetApp.getUi().alert('"progress" 탭을 찾을 수 없습니다.');
    return;
  }

  // 기존 progress 탭의 보호 범위만 정리
  const existing = ss.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  for (const p of existing) {
    if (p.getRange().getSheet().getName() === "progress") {
      const desc = p.getDescription();
      if (desc === "PROGRESS_STATS_AND_HEADER" || desc === "PROGRESS_FIXED_COLS" || desc.includes("progress")) {
        p.remove();
      }
    }
  }

  // 1. 1-4행 보호 (통계 및 헤더)
  const headerRange = sheet.getRange(1, 1, 4, sheet.getMaxColumns());
  const headerProtection = headerRange.protect();
  headerProtection.setDescription("PROGRESS_STATS_AND_HEADER");
  headerProtection.removeEditors(headerProtection.getEditors());
  headerProtection.addEditor(me);
  if (headerProtection.canDomainEdit()) headerProtection.setDomainEdit(false);

  // 2. A-P열 (1-16열) 보호 (학번, 이름, 진도 수식)
  const fixedColsRange = sheet.getRange(1, 1, sheet.getMaxRows(), 16);
  const fixedColsProtection = fixedColsRange.protect();
  fixedColsProtection.setDescription("PROGRESS_FIXED_COLS");
  fixedColsProtection.removeEditors(fixedColsProtection.getEditors());
  fixedColsProtection.addEditor(me);
  if (fixedColsProtection.canDomainEdit()) fixedColsProtection.setDomainEdit(false);

  SpreadsheetApp.getUi().alert(
    "✅ progress 탭 보호 설정 완료\n" +
    "- 1-4행 (통계 및 헤더) 보호 완료\n" +
    "- A-P열 (학번/성명/진도) 보호 완료\n" +
    "- Q열(한타04) 이후 학생 입력란 개방 완료"
  );
}

/**
 * score 탭을 정렬합니다.
 * 정렬 기준: 1차 주차(B열) 역순 → 2차 유형1(F열) → 3차 유형2(G열) → 4차 학번(C열) 오름차순
 * No(A열)는 맨 위부터 N down to 1로 재부여합니다.
 */
function sortScoreTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SCORE_TAB_NAME);

  if (!sheet) {
    SpreadsheetApp.getUi().alert("score 탭을 찾을 수 없습니다.");
    return;
  }

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();

  if (lastRow < 2) {
    SpreadsheetApp.getUi().alert("정렬할 데이터가 없습니다.");
    return;
  }

  // 헤더 제외, 2행부터 데이터 범위
  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);

  // 정렬: B열(주차) 역순 → F열(유형1) → G열(유형2) → C열(학번)
  dataRange.sort([
    { column: 2, ascending: false }, // 주차 역순
    { column: 6, ascending: true },  // 유형1
    { column: 7, ascending: true },  // 유형2
    { column: 3, ascending: true },  // 학번
  ]);

  // No 재부여: 맨 위 = N, 맨 아래 = 1
  const total = lastRow - 1;
  const noValues = [];
  for (let i = 0; i < total; i++) {
    noValues.push([total - i]);
  }
  sheet.getRange(2, 1, total, 1).setValues(noValues);

  SpreadsheetApp.getUi().alert(
    "✅ score 탭 정렬 완료\n" +
    `${total}행 정렬 (주차 역순 → 학번 오름차순)\n` +
    "No 재부여 완료"
  );
}
