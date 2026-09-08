/**
 * 시트를 열 때마다 구글 시트 상단에 'Q&A 알림 설정' 메뉴를 추가합니다.
 * 이 메뉴를 통해 사용자가 직접 트리거를 켤 수 있습니다.
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Q&A 알림 설정')
    .addItem('새 질문 자동 감지(onChange) 켜기', 'createOnChangeTrigger')
    .addSeparator()
    .addItem('🔒 1행 + D열 보호 설정 (학생 수정 차단)', 'protectHeaderAndColumnD')
    .addToUi();
}

function checkNewQuestionsAndNotify() {
  // 실제 시트의 탭 이름으로 변경해주세요. (예: "Q&A", "설문응답" 등)
  const SHEET_NAME = "Q&A";

  // 알림을 받을 본인 이메일 주소로 변경해주세요.
  const EMAIL_ADDRESS = "wonhyukc@stu.ac.kr";

  // 현재 스크립트가 포함된 스프레드시트를 활성화합니다.
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  if (!ss) {
    console.error("이 스크립트는 구글 시트 내부(확장 프로그램 > Apps Script)에서 실행되어야 합니다.");
    return;
  }

  const sheet = ss.getSheetByName(SHEET_NAME);

  if (!sheet) {
    console.error(`Sheet name "${SHEET_NAME}" not found.`);
    return;
  }

  const startRow = 2; // 데이터가 시작하는 행 (헤더가 1행인 경우 2행부터)
  const lastRow = sheet.getLastRow();

  if (lastRow < startRow) return;

  // A열(1)부터 D열(4)까지 가져옵니다. 
  // 실제 D열에 '알림상태' 열을 만드셔야 합니다.
  const dataRange = sheet.getRange(startRow, 1, lastRow - 1, 4);
  const data = dataRange.getValues();

  let newQuestions = [];
  let newQuestionRows = []; // 행 인덱스를 별도로 추적

  for (let i = 0; i < data.length; i++) {
    const question = String(data[i][0] || "").trim(); // A열
    const answer = String(data[i][1] || "").trim();   // B열
    const notifyStatus = String(data[i][3] || "").trim(); // D열

    // 질문은 있고, 답변은 비어있고, 발송됨 상태가 아닐 때
    if (question !== "" && answer === "" && notifyStatus !== "발송됨") {
      newQuestions.push(question);
      newQuestionRows.push(i); // D열 마킹을 나중에 하기 위해 행 인덱스 저장
    }
  }

  if (newQuestions.length > 0) {
    let message = `답변이 없는 새로운 질문이 ${newQuestions.length}건 있습니다.\n\n`;
    message += `시트 링크:\n${ss.getUrl()}\n\n`;
    message += "--- 새 질문 내용 ---\n";

    for (const q of newQuestions) {
      message += `- ${q}\n`;
    }

    try {
      MailApp.sendEmail(EMAIL_ADDRESS, "[알림] Q&A 시트에 새 질문이 있습니다!", message);

      // ✅ 이메일 발송 성공 후에만 D열에 '발송됨' 마킹
      for (const rowIndex of newQuestionRows) {
        sheet.getRange(startRow + rowIndex, 4).setValue("발송됨");
      }
    } catch (e) {
      // 발송 실패 시 D열을 건드리지 않아 다음 실행에서 재시도됨
      console.error("이메일 발송 실패:", e);
    }
  }
}

/**
 * 시트에 새로운 내용이 추가(변경)될 때마다 즉시 확인하는 트리거를 생성합니다.
 * 구글 앱스 스크립트 웹 화면에서 이 함수를 딱 한 번만 실행해주면 됩니다.
 */
function createOnChangeTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const trigger of triggers) {
    if (trigger.getHandlerFunction() === "checkNewQuestionsAndNotify") {
      ScriptApp.deleteTrigger(trigger);
    }
  }

  ScriptApp.newTrigger("checkNewQuestionsAndNotify")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onChange()
    .create();

  console.log("새 질문 즉시 감지 트리거(onChange) 설정 완료.");
}

/**
 * 이 스프레드시트 내 "Q&A"가 포함된 모든 탭의
 * 1행(헤더)과 D열(알림상태)에 보호를 설정합니다.
 * 소유자(스크립트 실행자)만 편집 가능하며, 학생은 수정 불가합니다.
 * 메뉴에서 딱 한 번만 실행하면 됩니다.
 */
function protectHeaderAndColumnD() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const me = Session.getEffectiveUser();

  // "Q&A"가 포함된 탭 전부 찾기
  const qaSheets = ss.getSheets().filter(s => s.getName().includes("Q&A"));

  if (qaSheets.length === 0) {
    SpreadsheetApp.getUi().alert('이 스프레드시트에 "Q&A" 탭이 없습니다.');
    return;
  }

  // 기존 보호 중 Q&A 탭에 걸린 것 제거 (중복 방지)
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
    console.log(`보호 설정: ${name} - 1행(QA_HEADER_ROW), D열(QA_NOTIFY_COL)`);
  }

  SpreadsheetApp.getUi().alert(results.join("\n") + "\n\n교수님만 수정 가능합니다.");
}
