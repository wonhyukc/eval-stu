/**
 * 파이썬 4반 성적 시트 정렬 메뉴
 * score 탭을 주차 역순 → 학번 오름차순으로 정렬하고 No를 재부여합니다.
 */

const SCORE_TAB_NAME = "score";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("관리자 설정")
    .addItem("🔄 score 탭 정렬 (주차↓ 학번↑)", "sortScoreTab")
    .addToUi();
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
