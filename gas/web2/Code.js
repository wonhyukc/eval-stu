/**
 * 스프레드시트 ID 정의 (코드 최상단 전역 변수)
 * 2반(web2)이 마스터(SSOT) 원본 시트입니다.
 */
const MASTER_SPREADSHEET_ID = "1OMeWuYt45TZMygmkh5hOhqSCCUFYJv4iE0hTY554iAo"; // 2반 (web2) 마스터
const SPREADSHEET_ID_WEB1 = "1pVbDITgW07ErTS4sQHDt1edVDCVKXrLAeRG3fF7-fAk";   // 1반 (web1)
const SPREADSHEET_ID_WEB2 = MASTER_SPREADSHEET_ID;

// 동기화 대상 스프레드시트 ID 목록 (2반 마스터 내용을 배포할 대상)
const TARGET_SPREADSHEET_IDS = [
  SPREADSHEET_ID_WEB1
];

/**
 * 2반 시트 기준 공식 탭 목록 및 고정 순서 (1반/2반 공통)
 */
const ALLOWED_SHEET_ORDER = [
  "resource",
  "progress",
  "Q&A",
  "score",
  "grade",
  "peer-eval-submissions",
  "peer-eval",
  "agenda"
];

/**
 * 시트를 열 때마다 구글 시트 상단에 '관리자 설정' 메뉴를 추가합니다.
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('관리자 설정')
    .addItem('⚡ 새 질문 감지 & 시트 구조 방어(onChange) 트리거 켜기', 'createOnChangeTrigger')
    .addSeparator()
    .addItem('📋 resource 탭 동기화 (1행 보존, 2행부터 복사)', 'syncResourceTab')
    .addItem('🔄 시트 순서 지금 정렬 및 미허용 탭 삭제', 'manualEnforceStructure')
    .addItem('🔒 Q&A 1행 + D열 보호 설정 (학생 수정 차단)', 'protectHeaderAndColumnD')
    .addItem('🔒 progress 1-4행 + 고정열 보호 설정', 'protectProgressTab')
    .addItem('🔑 서비스 계정 권한 부여 & grade 수식/헤더 동기화', 'syncServiceAccountAndGradeTab')
    .addSeparator()
    .addItem('🔄 score 탭 정렬 (주차↓ 학번↑)', 'sortScoreTab')
    .addToUi();
}

/**
 * 2반(마스터) 시트의 'resource' 탭 내용을 1반 시트의 'resource' 탭으로 복사 및 동기화합니다.
 * ⚠️ 1행(반별 고유 링크 및 개별 안내)은 건드리지 않고 100% 보존하며, 2행부터의 공통 리소스만 안전하게 동기화합니다.
 */
function syncResourceTab() {
  const masterSS = SpreadsheetApp.openById(MASTER_SPREADSHEET_ID);
  const sourceSheet = masterSS.getSheetByName("resource");

  if (!sourceSheet) {
    const msg = "2반(마스터) 시트에 'resource' 탭이 없습니다.";
    console.error(msg);
    try { SpreadsheetApp.getUi().alert(msg); } catch (e) {}
    return;
  }

  const startRow = 2; // 1행 보존을 위해 2행부터 시작
  const lastRow = sourceSheet.getLastRow();

  if (lastRow < startRow) {
    const msg = "2반 마스터 시트에 복사할 2행 이하 데이터가 없습니다.";
    console.log(msg);
    try { SpreadsheetApp.getUi().alert(msg); } catch (e) {}
    return;
  }

  const numRows = lastRow - startRow + 1;
  const numCols = sourceSheet.getLastColumn() || 1;

  // 1. 2반 마스터에서 2행부터 데이터, 하이퍼링크, 서식 추출
  const sourceRange = sourceSheet.getRange(startRow, 1, numRows, numCols);
  const richTexts = sourceRange.getRichTextValues();
  const backgrounds = sourceRange.getBackgrounds();
  const fontWeights = sourceRange.getFontWeights();
  const fontColors = sourceRange.getFontColors();
  const horizontalAlignments = sourceRange.getHorizontalAlignments();
  const verticalAlignments = sourceRange.getVerticalAlignments();

  // 열 너비 추출
  const colWidths = [];
  for (let c = 1; c <= numCols; c++) {
    colWidths.push(sourceSheet.getColumnWidth(c));
  }

  // 2. 대상 시트들(1반)의 2행부터 데이터 주입 (1행은 보존)
  let syncCount = 0;
  TARGET_SPREADSHEET_IDS.forEach(id => {
    try {
      const targetSS = SpreadsheetApp.openById(id);
      let targetSheet = targetSS.getSheetByName("resource");

      if (!targetSheet) {
        targetSheet = targetSS.insertSheet("resource", 1);
      }

      // 1행은 건드리지 않고 2행부터의 기존 데이터만 클리어
      const targetLastRow = targetSheet.getLastRow();
      if (targetLastRow >= startRow) {
        targetSheet.getRange(startRow, 1, targetLastRow - startRow + 1, targetSheet.getMaxColumns()).clear();
      }

      // 행/열 부족 시 확장
      const requiredRows = startRow + numRows - 1;
      if (targetSheet.getMaxRows() < requiredRows) {
        targetSheet.insertRowsAfter(targetSheet.getMaxRows(), requiredRows - targetSheet.getMaxRows());
      }
      if (targetSheet.getMaxColumns() < numCols) {
        targetSheet.insertColumnsAfter(targetSheet.getMaxColumns(), numCols - targetSheet.getMaxColumns());
      }

      // 2행부터 데이터 및 서식 주입
      const targetRange = targetSheet.getRange(startRow, 1, numRows, numCols);
      targetRange.setBackgrounds(backgrounds);
      targetRange.setFontWeights(fontWeights);
      targetRange.setFontColors(fontColors);
      targetRange.setHorizontalAlignments(horizontalAlignments);
      targetRange.setVerticalAlignments(verticalAlignments);
      targetRange.setRichTextValues(richTexts);

      // 열 너비 반영
      for (let c = 0; c < colWidths.length; c++) {
        targetSheet.setColumnWidth(c + 1, colWidths[c]);
      }

      // 혹시 이전에 생겼던 임시 사본 시트가 있다면 정리
      const copySheet = targetSS.getSheetByName("resource의 사본") || targetSS.getSheetByName("Copy of resource");
      if (copySheet) {
        try { targetSS.deleteSheet(copySheet); } catch (e) {}
      }

      syncCount++;
      console.log(`[리소스 동기화 성공] 2반(마스터) -> 대상(${id}) (2행~${requiredRows}행)`);
    } catch (err) {
      console.error(`[리소스 동기화 실패] 대상 ID: ${id}, 에러: ${err.message}`);
    }
  });

  const alertMsg = `✅ 2반(마스터)의 resource 2행 이하 내용이 1반으로 안전하게 동기화되었습니다. (1행 고유정보 보존됨)`;
  console.log(alertMsg);
  try { SpreadsheetApp.getUi().alert(alertMsg); } catch (e) {}
}

/**
 * 스프레드시트의 onChange 이벤트를 처리하는 통합 핸들러 함수입니다.
 * 1) 임의 시트 생성 감지 시 삭제 & 탭 순서 강제 복구
 * 2) Q&A 새 질문 감지 시 이메일 알림 발송
 * 3) score 탭 자동 정렬 (API 업로드 후 60초 쓰로틀)
 */
function onSpreadsheetChange(e) {
  try {
    enforceWorkbookStructure(e);
  } catch (err) {
    console.error("시트 구조 방어 실행 중 오류:", err);
  }

  try {
    checkNewQuestionsAndNotify();
  } catch (err) {
    console.error("Q&A 알림 확인 중 오류:", err);
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
  const sheet = ss.getSheetByName("score");
  if (!sheet) return;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return;

  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);
  dataRange.sort([
    { column: 2, ascending: false },
    { column: 6, ascending: true },
    { column: 7, ascending: true },
    { column: 3, ascending: true },
  ]);

  const total = lastRow - 1;
  const noValues = [];
  for (let i = 0; i < total; i++) {
    noValues.push([total - i]);
  }
  sheet.getRange(2, 1, total, 1).setValues(noValues);
  console.log(`[자동 정렬] score 탭 ${total}행 정렬 완료`);
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

function checkNewQuestionsAndNotify() {
  const SHEET_NAME = "Q&A";
  const EMAIL_ADDRESS = "wonhyukc@stu.ac.kr";

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) return;

  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) return;

  const startRow = 2; // 헤더 제외 2행부터
  const lastRow = sheet.getLastRow();
  if (lastRow < startRow) return;

  // A열(1)부터 D열(4)까지 조회
  const dataRange = sheet.getRange(startRow, 1, lastRow - 1, 4);
  const data = dataRange.getValues();

  let newQuestions = [];
  let newQuestionRows = [];

  for (let i = 0; i < data.length; i++) {
    const question = String(data[i][0] || "").trim(); // A열 (질문)
    const answer = String(data[i][1] || "").trim();   // B열 (답변)
    const notifyStatus = String(data[i][3] || "").trim(); // D열 (알림상태)

    if (question !== "" && answer === "" && notifyStatus !== "발송됨") {
      newQuestions.push(question);
      newQuestionRows.push(i);
    }
  }

  if (newQuestions.length > 0) {
    const sheetUrl = `${ss.getUrl()}?gid=${sheet.getSheetId()}#gid=${sheet.getSheetId()}`;
    let message = `답변이 없는 새로운 질문이 ${newQuestions.length}건 있습니다.\n\n`;
    message += `시트 링크:\n${sheetUrl}\n\n`;
    message += "--- 새 질문 내용 ---\n";

    for (const q of newQuestions) {
      message += `- ${q}\n`;
    }

    try {
      MailApp.sendEmail(EMAIL_ADDRESS, "[알림] Q&A 시트에 새 질문이 있습니다!", message);

      for (const rowIndex of newQuestionRows) {
        sheet.getRange(startRow + rowIndex, 4).setValue("발송됨");
      }
    } catch (e) {
      console.error("이메일 발송 실패:", e);
    }
  }
}

/**
 * 시트 수정 시(onChange) 통합 핸들러(onSpreadsheetChange)를 자동 실행하는 설치형 트리거를 생성합니다.
 */
function createOnChangeTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    const fn = trigger.getHandlerFunction();
    if (fn === "onSpreadsheetChange" || fn === "checkNewQuestionsAndNotify" || fn === "enforceWorkbookStructure") {
      ScriptApp.deleteTrigger(trigger);
    }
  }

  ScriptApp.newTrigger("onSpreadsheetChange")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();

  console.log("시트 변경 감지 트리거(onSpreadsheetChange) 설정 완료.");
  SpreadsheetApp.getUi().alert("⚡ onChange 트리거가 성공적으로 활성화되었습니다.");
}

/**
 * 이 스프레드시트 내 "Q&A"가 포함된 모든 탭의
 * 1행(헤더)과 D열(알림상태)에 보호를 설정합니다.
 */
function protectHeaderAndColumnD() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const me = Session.getEffectiveUser();

  const qaSheets = ss.getSheets().filter(s => s.getName().includes("Q&A"));

  if (qaSheets.length === 0) {
    SpreadsheetApp.getUi().alert('이 스프레드시트에 "Q&A" 탭이 없습니다.');
    return;
  }

  const existing = ss.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  for (const p of existing) {
    const sheetName = p.getRange().getSheet().getName();
    if (sheetName.includes("Q&A")) {
      const desc = p.getDescription();
      if (desc === "QA_HEADER_ROW" || desc === "QA_NOTIFY_COL") {
        p.remove();
      }
    }
  }

  const results = [];

  const serviceAccount = "driveapi@drive-project-84200.iam.gserviceaccount.com";

  for (const sheet of qaSheets) {
    const name = sheet.getName();

    // D1 헤더 영문화 강제
    sheet.getRange(1, 4).setValue("Email Status");

    // 1행 보호 (헤더)
    const headerRange = sheet.getRange(1, 1, 1, sheet.getLastColumn() || 10);
    const headerProtection = headerRange.protect();
    headerProtection.setDescription("QA_HEADER_ROW");
    headerProtection.removeEditors(headerProtection.getEditors());
    headerProtection.addEditor(me);
    try { headerProtection.addEditor(serviceAccount); } catch (e) {}
    if (headerProtection.canDomainEdit()) headerProtection.setDomainEdit(false);

    // D열 전체 보호 (알림상태)
    const colDRange = sheet.getRange(1, 4, sheet.getMaxRows(), 1);
    const colDProtection = colDRange.protect();
    colDProtection.setDescription("QA_NOTIFY_COL");
    colDProtection.removeEditors(colDProtection.getEditors());
    colDProtection.addEditor(me);
    try { colDProtection.addEditor(serviceAccount); } catch (e) {}
    if (colDProtection.canDomainEdit()) colDProtection.setDomainEdit(false);

    results.push(`✅ [${name}] 1행 + D열 보호 완료 (서비스 계정 허용됨)`);
  }

  SpreadsheetApp.getUi().alert(results.join("\n") + "\n\n교수님만 수정 가능합니다.");
}

/**
 * score 탭을 정렬합니다.
 * 정렬 기준: 1차 주차(B열) 역순 → 2차 유형1(F열) → 3차 유형2(G열) → 4차 학번(C열) 오름차순
 * No(A열)는 맨 위부터 N down to 1로 재부여합니다.
 */
function sortScoreTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("score");

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

  const dataRange = sheet.getRange(2, 1, lastRow - 1, lastCol);

  dataRange.sort([
    { column: 2, ascending: false },
    { column: 6, ascending: true },
    { column: 7, ascending: true },
    { column: 3, ascending: true },
  ]);

  const total = lastRow - 1;
  const noValues = [];
  for (let i = 0; i < total; i++) {
    noValues.push([total - i]);
  }
  sheet.getRange(2, 1, total, 1).setValues(noValues);

  SpreadsheetApp.getUi().alert(
    "✅ score 탭 정렬 완료\n" +
    `${total}행 (주차 역순 → 학번 오름차순)\nNo 재부여 완료`
  );
}

/**
 * progress 탭 표준 보호 설정 (웹 2반)
 * - 1-4행 (mean, stdev, count, 헤더): 보호
 * - A-J열 (1-10열): 보호
 * - K열(wpm04) 이후 학생 입력 영역: 편집 허용
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

  // 2. A-J열 (1-10열) 보호
  const fixedColsRange = sheet.getRange(1, 1, sheet.getMaxRows(), 10);
  const fixedColsProtection = fixedColsRange.protect();
  fixedColsProtection.setDescription("PROGRESS_FIXED_COLS");
  fixedColsProtection.removeEditors(fixedColsProtection.getEditors());
  fixedColsProtection.addEditor(me);
  if (fixedColsProtection.canDomainEdit()) fixedColsProtection.setDomainEdit(false);

  SpreadsheetApp.getUi().alert(
    "✅ progress 탭 보호 설정 완료\n- 1-4행 (통계/헤더): 보호\n- A-J열 (고정 정보): 보호\n- K열 이후: 학생 입력 허용"
  );
}

/**
 * 서비스 계정 권한 부여 및 grade 탭/영문 헤더 동기화 (웹 2반)
 */
function syncServiceAccountAndGradeTab() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const serviceAccount = "driveapi@drive-project-84200.iam.gserviceaccount.com";

  // 1. 모든 시트 및 범위 보호에서 서비스 계정을 editor로 추가
  const sheetProtections = ss.getProtections(SpreadsheetApp.ProtectionType.SHEET);
  for (const sp of sheetProtections) {
    try {
      sp.addEditor(serviceAccount);
    } catch (e) {
      console.warn("Sheet protection editor add failed:", e);
    }
  }
  const rangeProtections = ss.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  for (const rp of rangeProtections) {
    try {
      rp.addEditor(serviceAccount);
    } catch (e) {
      console.warn("Range protection editor add failed:", e);
    }
  }

  // 2. grade 탭 수식 업데이트 (D3:D34, E3:E34)
  const gradeSheet = ss.getSheetByName("grade");
  if (gradeSheet) {
    const lastRow = gradeSheet.getLastRow();
    for (let r = 3; r <= lastRow; r++) {
      gradeSheet.getRange(r, 4).setFormula(`=SUMIFS(score!$M:$M, score!$C:$C, $B${r}, score!$F:$F, "hw")`);
      gradeSheet.getRange(r, 5).setFormula(`=SUMIFS(score!$M:$M, score!$C:$C, $B${r}, score!$F:$F, "class")`);
    }
  }

  // 3. Q&A 탭 D1 영문화
  const qaSheet = ss.getSheetByName("Q&A");
  if (qaSheet) {
    qaSheet.getRange(1, 4).setValue("Email Status");
  }

  SpreadsheetApp.getUi().alert(
    "✅ 서비스 계정 권한 추가 및 grade 탭/영문 헤더 동기화 완료!"
  );
}


