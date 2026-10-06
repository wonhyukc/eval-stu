/**
 * 파이썬 4반 성적 시트 관리 (정렬 + 구조 방어)
 * score 탭을 주차 역순 → 학번 오름차순으로 정렬하고,
 * 허용되지 않은 탭 생성을 자동 차단합니다.
 */

const SCORE_TAB_NAME = "score";

/**
 * 4반 시트 기준 공식 탭 목록 및 고정 순서
 */
const ALLOWED_SHEET_ORDER = [
  "progress",
  "resource",
  "발표",
  "score",
  "agenda",
  "상호평가 제출자 답",
  "grade",
  "상호평가",
  "Q&A"
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("관리자 설정")
    .addItem("⚡ 자동 정렬 + 시트 구조 방어(onChange) 트리거 켜기", "createOnChangeTrigger")
    .addSeparator()
    .addItem("🔄 score 탭 정렬 (주차↓ 학번↑)", "sortScoreTab")
    .addItem("🔄 시트 순서 지금 정렬 및 미허용 탭 삭제", "manualEnforceStructure")
    .addSeparator()
    .addItem("🔒 progress 1-4행 + 고정열 보호 설정", "protectProgressTab")
    .addToUi();
}

/**
 * onChange 이벤트 설치형 트리거를 생성합니다.
 * 최초 1회만 실행하면 이후 score 탭 자동 정렬이 활성화됩니다.
 */
function createOnChangeTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    if (trigger.getHandlerFunction() === "onSpreadsheetChange") {
      ScriptApp.deleteTrigger(trigger);
    }
  }
  ScriptApp.newTrigger("onSpreadsheetChange")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();
  SpreadsheetApp.getUi().alert("⚡ onChange 트리거가 성공적으로 활성화되었습니다.\nscore 탭 자동 정렬이 켜졌습니다.");
}

/**
 * 스프레드시트 onChange 통합 핸들러.
 * 1) 임의 시트 생성 감지 시 삭제 & 탭 순서 강제 복구
 * 2) score 탭 자동 정렬 (API 업로드 후 60초 쓰로틀)
 */
function onSpreadsheetChange(e) {
  try {
    enforceWorkbookStructure(e);
  } catch (err) {
    console.error("시트 구조 방어 실행 중 오류:", err);
  }

  try {
    autoSortScoreTabSilent();
  } catch (err) {
    console.error("score 탭 자동 정렬 중 오류:", err);
  }
}

/**
 * score 탭을 자동 정렬합니다. (60초 쓰로틀 — 연속 이벤트 중복 실행 방지)
 * UI alert 없이 조용히 실행되며, 수동 실행은 sortScoreTab() 메뉴를 사용합니다.
 */
function autoSortScoreTabSilent() {
  const THROTTLE_MS = 60 * 1000;
  const props = PropertiesService.getScriptProperties();
  const lastSort = parseInt(props.getProperty("LAST_SCORE_SORT_TS") || "0");
  const now = Date.now();
  if (now - lastSort < THROTTLE_MS) {
    console.log("score 자동 정렬 스킵 (60초 이내 중복 실행 방지)");
    return;
  }
  props.setProperty("LAST_SCORE_SORT_TS", String(now));

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SCORE_TAB_NAME);
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return;

  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);
  dataRange.sort([
    { column: 2, ascending: false },
    { column: 7, ascending: true },
    { column: 8, ascending: true },
    { column: 3, ascending: true },
  ]);

  const total = lastRow - 1;
  console.log(`[자동 정렬] score 탭 ${total}행 정렬 완료 (원래 No 값 유지)`);
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
 * 정렬 기준: 1차 주차(B열) 역순 → 2차 유형1(G열) → 3차 유형2(H열) → 4차 학번(C열) 오름차순
 * 원래 No 번호를 유지합니다.
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

  // 정렬: B열(주차) 역순 → G열(유형1) → H열(유형2) → C열(학번)
  dataRange.sort([
    { column: 2, ascending: false }, // 주차 역순
    { column: 7, ascending: true },  // 유형1 (G열)
    { column: 8, ascending: true },  // 유형2 (H열)
    { column: 3, ascending: true },  // 학번 (C열)
  ]);

  const total = lastRow - 1;
  SpreadsheetApp.getUi().alert(
    "✅ score 탭 정렬 완료\n" +
    `${total}행 정렬 (주차 역순 → 학번 오름차순)\n` +
    "원래 No 번호 유지"
  );
}

/**
 * 허용되지 않은 새 시트가 생성되었는지 검사하여 즉시 삭제하고,
 * 탭 순서가 바뀌었을 경우 ALLOWED_SHEET_ORDER 순서대로 강제 원복합니다.
 */
function enforceWorkbookStructure(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = ss.getSheets();

  // 1. 허용되지 않은 새 시트가 생성되었는지 검사 후 즉시 삭제
  for (let i = sheets.length - 1; i >= 0; i--) {
    const sheet = sheets[i];
    const sheetName = sheet.getName();

    // 공식 목록에 없는 탭(새로 만든 탭)이면 삭제
    if (!ALLOWED_SHEET_ORDER.includes(sheetName)) {
      if (ss.getSheets().length > 1) {
        console.warn(`[구조 방어] 허용되지 않은 탭 감지 및 삭제: ${sheetName}`);
        ss.deleteSheet(sheet);
      }
    }
  }

  // 2. 탭 순서 강제 원복
  let targetIndex = 1;
  ALLOWED_SHEET_ORDER.forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (sheet) {
      sheet.activate();
      ss.moveActiveSheet(targetIndex);
      targetIndex++;
    }
  });
}

/**
 * 관리자 메뉴에서 수동으로 시트 순서 정렬 및 비인가 탭 삭제를 실행합니다.
 */
function manualEnforceStructure() {
  enforceWorkbookStructure(null);
  SpreadsheetApp.getUi().alert("✅ 탭 순서 정렬 및 미허용 탭 정리가 완료되었습니다.");
}
