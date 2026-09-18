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
  "progess",
  "Q&A",
  "score",
  "grade",
  "peer-eval-web",
  "peer-eval-list",
  "peer-eval-assignment",
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
    .addItem('📋 resource 탭 2반(마스터) 기준으로 동기화/배포', 'syncResourceTab')
    .addItem('🔄 시트 순서 지금 정렬 및 미허용 탭 삭제', 'manualEnforceStructure')
    .addItem('🔒 Q&A 1행 + D열 보호 설정 (학생 수정 차단)', 'protectHeaderAndColumnD')
    .addToUi();
}

/**
 * 2반(마스터) 시트의 'resource' 탭 내용을 1반 시트의 'resource' 탭으로 복사 및 동기화합니다.
 * 파일 간 copyTo 제약 오류를 방지하기 위해 RichText 및 서식 단위로 안전하게 덮어씁니다.
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

  // 1. 2반 마스터에서 데이터, 하이퍼링크, 서식, 열 너비 전부 추출
  const sourceRange = sourceSheet.getDataRange();
  const numRows = sourceRange.getNumRows();
  const numCols = sourceRange.getNumColumns();

  const richTexts = sourceRange.getRichTextValues();
  const backgrounds = sourceRange.getBackgrounds();
  const fontWeights = sourceRange.getFontWeights();
  const fontColors = sourceRange.getFontColors();
  const horizontalAlignments = sourceRange.getHorizontalAlignments();
  const verticalAlignments = sourceRange.getVerticalAlignments();

  const colWidths = [];
  for (let c = 1; c <= numCols; c++) {
    colWidths.push(sourceSheet.getColumnWidth(c));
  }

  // 2. 대상 시트들(1반)에 안전하게 데이터 및 서식 주입
  let syncCount = 0;
  TARGET_SPREADSHEET_IDS.forEach(id => {
    try {
      const targetSS = SpreadsheetApp.openById(id);
      let targetSheet = targetSS.getSheetByName("resource");

      if (!targetSheet) {
        targetSheet = targetSS.insertSheet("resource", 1);
      }

      // 기존 내용 클리어
      targetSheet.clear();

      // 행/열 부족 시 확장
      const targetMaxRows = targetSheet.getMaxRows();
      if (targetMaxRows < numRows) {
        targetSheet.insertRowsAfter(targetMaxRows, numRows - targetMaxRows);
      }
      const targetMaxCols = targetSheet.getMaxColumns();
      if (targetMaxCols < numCols) {
        targetSheet.insertColumnsAfter(targetMaxCols, numCols - targetMaxCols);
      }

      const targetRange = targetSheet.getRange(1, 1, numRows, numCols);

      // 서식 및 리치 텍스트(하이퍼링크 포함) 복사
      targetRange.setBackgrounds(backgrounds);
      targetRange.setFontWeights(fontWeights);
      targetRange.setFontColors(fontColors);
      targetRange.setHorizontalAlignments(horizontalAlignments);
      targetRange.setVerticalAlignments(verticalAlignments);
      targetRange.setRichTextValues(richTexts);

      // 열 너비 복사
      for (let c = 0; c < colWidths.length; c++) {
        targetSheet.setColumnWidth(c + 1, colWidths[c]);
      }

      // 혹시 임시 생성되었던 사본 시트가 있으면 삭제
      const copySheet = targetSS.getSheetByName("resource의 사본") || targetSS.getSheetByName("Copy of resource");
      if (copySheet) {
        try { targetSS.deleteSheet(copySheet); } catch (e) {}
      }

      syncCount++;
      console.log(`[리소스 동기화 성공] 2반(마스터) -> 대상(${id})`);
    } catch (err) {
      console.error(`[리소스 동기화 실패] 대상 ID: ${id}, 에러: ${err.message}`);
    }
  });

  const alertMsg = `✅ 2반(마스터)의 resource 탭이 1반 시트로 완벽히 동기화되었습니다. (${syncCount}개 반영)`;
  console.log(alertMsg);
  try { SpreadsheetApp.getUi().alert(alertMsg); } catch (e) {}
}

/**
 * 스프레드시트의 onChange 이벤트를 처리하는 통합 핸들러 함수입니다.
 * 1) 임의 시트 생성 감지 시 삭제 & 탭 순서 강제 복구
 * 2) Q&A 새 질문 감지 시 이메일 알림 발송
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

  for (const sheet of qaSheets) {
    const name = sheet.getName();

    // 1행 보호 (헤더)
    const headerRange = sheet.getRange(1, 1, 1, sheet.getLastColumn() || 10);
    const headerProtection = headerRange.protect();
    headerProtection.setDescription("QA_HEADER_ROW");
    headerProtection.removeEditors(headerProtection.getEditors());
    headerProtection.addEditor(me);
    if (headerProtection.canDomainEdit()) headerProtection.setDomainEdit(false);

    // D열 전체 보호 (알림상태)
    const colDRange = sheet.getRange(1, 4, sheet.getMaxRows(), 1);
    const colDProtection = colDRange.protect();
    colDProtection.setDescription("QA_NOTIFY_COL");
    colDProtection.removeEditors(colDProtection.getEditors());
    colDProtection.addEditor(me);
    if (colDProtection.canDomainEdit()) colDProtection.setDomainEdit(false);

    results.push(`✅ [${name}] 1행 + D열 보호 완료`);
  }

  SpreadsheetApp.getUi().alert(results.join("\n") + "\n\n교수님만 수정 가능합니다.");
}
