module.exports = {
  title: "Student Guide",
  subtitle: "Taking your exam with the ExamProctor app",
  audience: "For students. It shows every screen you will see, from installing the app to finishing your exam, and what to do if something goes wrong. A short guide in Bangla is on the last page.",
  version: "Version 1.0",
  date: "October 2026",
  footer: "Student guide",
  intro: "Do sections 2 and 3 a day before the exam, not on the day. Sections 5 and 6 explain what happens during the exam.",
  sections: [
    {
      title: "Before you begin",
      blocks: [
        { p: "ExamProctor is the app you use to take your exam. It opens your exam (a Google Form and/or a practical task) and quietly keeps a record so that the exam is fair for everyone. Your teacher sees that record; other students do not." },
        { h: "What to expect" },
        { ul: [
          "Your exam may have a <b>written part</b> (a Google Form in a locked, full-screen window) and/or a <b>practical part</b> (you work in your own apps). If both, the written part comes first.",
          "When you leave the exam window during the written part, a <b>screenshot</b> is taken and your teacher is told.",
          "If your teacher asked for it, the app also takes <b>webcam photos</b> now and then.",
          "You can log in again if your computer crashes. You do not lose your place.",
        ] },
        { h: "Checklist for exam day" },
        { table: { head: ["Do", "Why"], rows: [
          ["Install the app and log in <b>the day before</b>", "So any problem is fixed before the exam."],
          ["Plug in your charger and use a stable internet connection", "The exam runs on the internet."],
          ["Use <b>one screen</b> only (unplug extra monitors)", "The written part will not start with a second screen."],
          ["Quit screen-sharing, remote-access and recording apps (OBS, TeamViewer, AnyDesk, Parsec and similar)", "They are not allowed and the exam will not start while they run."],
          ["Allow <b>Screen Recording</b> (and the <b>Camera</b>, if required)", "The app needs them for the evidence."],
          ["Know your roll number and password", "You need them to log in."],
          ["Sit somewhere quiet and close other apps and chats", "Leaving the exam window is recorded."],
        ] } },
        { note: "This guide covers the Mac app. If you use Windows, ask your teacher.", title: "Which computer?" },
      ],
    },
    {
      title: "Install the app (Mac)",
      blocks: [
        { ol: [
          "Download the <b>ExamProctor</b> file (it ends in <code>.dmg</code>) from the link your teacher shared.",
          "Double-click it. A window opens showing the app and the Applications folder.",
          "<b>Drag ExamProctor onto Applications.</b>",
          "Open <b>Applications</b> and start <b>ExamProctor</b>.",
        ] },
        { img: "student/09-install-window.png", caption: "Illustration: drag the app onto the Applications folder" },
        { h: "If your Mac says it cannot verify the app" },
        { p: "This is normal: the app is not sold through the App Store. You only have to do this once." },
        { table: { head: ["Your Mac", "What to do"], rows: [
          ["macOS 15 (Sequoia) or newer", "Open <b>System Settings</b>, then <b>Privacy &amp; Security</b>. Scroll down and press <b>Open Anyway</b> next to ExamProctor. Confirm."],
          ["macOS 14 or older", "Right-click the app, choose <b>Open</b>, then press <b>Open</b> again."],
          ["Still blocked", "Open <b>Terminal</b> and run:<br><code>xattr -dr com.apple.quarantine /Applications/ExamProctor.app</code>"],
        ] } },
        { h: "Allow Screen Recording (and Camera)" },
        { ol: [
          "Open <b>System Settings</b>, then <b>Privacy &amp; Security</b>.",
          "Open <b>Screen &amp; System Audio Recording</b> and switch <b>ExamProctor</b> on. (If your exam uses the webcam, also open <b>Camera</b> and switch it on.)",
          "<b>Quit the app and open it again.</b> The setting only takes effect after a restart.",
        ] },
        { note: "If you forget, the app tells you when you press <b>Begin exam</b>, and it will not start until it is allowed.", title: "Don't worry" },
      ],
    },
    {
      title: "Log in",
      blocks: [
        { h: "1. The notice" },
        { img: "student/01-consent.png", size: "side", caption: "The first screen", legend: ["Read it and press <b>Start Exam</b>. It tells you the exam is proctored: a screenshot is taken when you switch away from the exam window."] },
        { h: "2. Your roll number and password" },
        { img: "student/02-login.png", size: "side", caption: "Log in", legend: [
          "Type your <b>roll number</b>.", "Type your <b>password</b>.", "Press <b>Log in</b>.", "First time? Press <b>Activate account</b> (below).",
        ] },
        { p: "If the details are wrong the app says so and you can try again. After five wrong tries from your computer you must wait 15 minutes." },
        { img: "student/03-login-error.png", size: "side", caption: "A wrong password", legend: ["The message tells you what is wrong. <i>Invalid roll number or password</i> means check both and try again."] },
        { h: "3. First time? Get your password" },
        { p: "You get your first password in one of two ways. Ask your teacher which one your school uses." },
        { cols: [
          { title: "A. Your teacher gives you a slip", html: "<p>Your teacher hands you a paper slip with your own password. Use it at the login screen with your roll number.</p>" },
          { title: "B. The app emails it to you", html: "<p>Press <b>First time? Activate account</b>, type your roll number and the email your school has for you, and press <b>Email me my password</b>. Check your inbox (and spam), then log in.</p>" },
        ] },
        { img: "student/04-activate.png", size: "side", caption: "Activate your account", legend: [
          "Your roll number.", "The email registered with your school.", "<b>Email me my password</b>.", "Back to the login screen.",
        ] },
        { note: "Your password is private. Never share it. You can change it any time in <b>My profile</b> (section 9).", kind: "warn", title: "Keep it secret" },
      ],
    },
    {
      title: "Choose your exam and start",
      blocks: [
        { img: "student/05-exam-list.png", size: "side", caption: "Your exams", legend: [
          "<b>My profile</b> (your details, change password) and <b>Log out</b>.",
          "The list shows the exams of <b>your batch</b>. Choose one.",
          "The start and end time of the chosen exam. You can only begin while it is open.",
          "<b>Begin exam</b>.",
        ] },
        { p: "When you press <b>Begin exam</b> the app first checks your computer. If everything is fine, the exam window opens." },
        { h: "If the exam does not start" },
        { table: { head: ["The app says", "What it means and what to do"], rows: [
          ["Disconnect extra monitors before starting the exam.", "Unplug the second screen, then try again."],
          ["Please close OBS Studio (or another app) before starting the exam.", "Quit that app completely (also its menu-bar icon), then try again."],
          ["Screen Recording permission is needed for this exam…", "Turn on ExamProctor in System Settings, Privacy &amp; Security, Screen &amp; System Audio Recording, then quit and reopen the app."],
          ["This exam requires your webcam. Camera access was denied.", "Allow the Camera for ExamProctor in System Settings, and close other apps that use the camera."],
          ["This exam has not started yet. / This exam has ended.", "Check the exam's start and end time on the exam list."],
          ["You quit this exam and cannot re-enter it.", "Quitting is final. Ask your teacher."],
          ["Your teacher ended your attempt.", "Ask your teacher to let you restart."],
          ["Cannot reach the exam server…", "Check your Wi-Fi or cable and try again."],
          ["Account not activated.", "You have no password yet: see section 3."],
        ] } },
      ],
    },
    {
      title: "The written part",
      blocks: [
        { p: "The exam window opens in <b>full screen</b> and shows your Google Form. Answer the questions as you normally would." },
        { img: "student/07-written-window.png", caption: "The written part (an example form)" },
        { h: "Rules during the written part" },
        { cols: [
          { title: "You can", html: "<ul><li>Answer all the questions</li><li>Scroll, type and select answers</li><li>Submit the form when you are done</li></ul>" },
          { title: "You cannot", html: "<ul><li>Copy, cut or paste</li><li>Open developer tools, print, save or view the page source</li><li>Go to other websites from the exam window</li><li>Leave full screen or switch to other apps without it being recorded</li><li>Use a second monitor or a screen-sharing, remote or recording app</li></ul>" },
        ] },
        { h: "What if I switch away?" },
        { p: "You are allowed to, but it is recorded. If you leave the exam window for more than about 3 seconds, a <b>screenshot is taken</b> and your teacher is told. When you come back, this question appears:" },
        { img: "student/d01-switched-away.png", size: "narrow", caption: "Illustration: the warning when you return" },
        { ul: [
          "<b>Return to exam</b> continues your exam. Do this unless you really want to stop.",
          "<b>Quit exam</b> ends your exam. <b>You will be marked 0.</b> You cannot go back in unless your teacher allows it.",
          "Leaving full screen, or trying to close the window, asks the same question.",
        ] },
        { note: "A very short switch (a few seconds) is ignored. Notifications that pop up do not matter unless you click away from the exam.", title: "Accidents" },
        { h: "Finishing the written part" },
        { p: "Press <b>Submit</b> on the form. The app notices it:" },
        { img: "student/d02-written-submitted.png", size: "narrow", caption: "Illustration: after you submit, if your exam has a practical part" },
        { ul: [
          "If there is a <b>practical part</b>, press <b>Start practical part</b>. You cannot go back to the written part.",
          "If the exam is written only, the app shows <i>Your answers were submitted</i> and closes. You are done.",
        ] },
      ],
    },
    {
      title: "The practical part",
      blocks: [
        { p: "The practical part opens in a <b>small normal window</b>. This is your control panel. Do your practical work in your own apps (a simulator, a spreadsheet, a code editor) and switch between them freely. Leaving the window is <b>not</b> a violation here." },
        { img: "student/08-practical-window.png", size: "side", caption: "The practical window", legend: [
          "<b>Time left</b>. It turns orange in the last five minutes.",
          "A reminder: a screenshot of your screen is taken about once a minute while you work.",
          "Your teacher's <b>instructions</b>.",
          "<b>Open task link</b>: opens the lab sheet or task page, if your teacher added one.",
          "<b>Finish practical</b>: press it only when you are completely done.",
        ] },
        { h: "Finishing" },
        { img: "student/d03-finish-practical.png", size: "narrow", caption: "Illustration: confirm that you are finished" },
        { ul: [
          "Make sure your work is saved and handed in the way your teacher told you (for example uploaded to the class drive).",
          "Press <b>Finish</b>. You cannot come back after this. Press <b>Keep working</b> if you are not done.",
          "Closing this window also asks whether you want to finish.",
        ] },
        { note: "You may use a second monitor in the practical part. Screen-sharing, remote-access and recording apps are still not allowed.", title: "Good to know" },
      ],
    },
    {
      title: "Time",
      blocks: [
        { ul: [
          "Your exam has an <b>end time</b>. The practical window shows a countdown.",
          "When time is up, the app tells you and closes your exam window. Make sure you have submitted before then.",
          "If you lost time (a crash, power cut or internet problem), tell your teacher. They can give you <b>extra minutes</b> that apply only to you; your app picks it up within about two minutes.",
        ] },
        { img: "student/d04-time-up.png", size: "narrow", caption: "Illustration: when the time is over" },
        { note: "Submit the Google Form <b>before</b> time runs out. When the exam closes you can no longer submit.", kind: "warn", title: "Submit early" },
      ],
    },
    {
      title: "If something goes wrong",
      blocks: [
        { table: { head: ["What happened", "What to do"], rows: [
          ["<b>The internet dropped</b>", "Keep the exam window open and reconnect. The app saves everything and sends it when you are back online. Your Google Form page stays as it is; submit once you are connected. Tell your teacher if you lost time."],
          ["<b>The app or the computer crashed</b>", "Open the app, log in again and press <b>Begin exam</b>. You continue in the same part you were in. Tell your teacher so they can add time if needed."],
          ["<b>The laptop went to sleep</b>", "Wake it. The app reconnects. The clock kept running while it slept."],
          ["<b>I forgot my password</b>", "Ask your teacher for a new one. The old one stops working."],
          ["<b>I pressed Quit by mistake</b>", "Ask your teacher straight away: quitting is final until they allow a restart."],
          ["<b>\"Your session has ended\"</b>", "You logged in somewhere else, or your teacher ended your session. Ask your teacher."],
          ["<b>\"Please close …\" during the exam</b>", "A screen-sharing, remote-access or recording app is running. Quit it now. It has been recorded."],
          ["<b>The camera does not work</b>", "Close other apps that use the camera, allow the Camera for ExamProctor, and tell your teacher."],
          ["<b>Nothing works</b>", "Stay calm, tell your teacher or invigilator, and do not try tricks. A problem you report is not a violation."],
        ] } },
        { pair: [
          { img: "student/d05-blocked-app.png", caption: "Illustration: a blocked app was found" },
          { img: "student/d06-session-ended.png", caption: "Illustration: your session ended" },
        ] },
      ],
    },
    {
      title: "My profile and password",
      blocks: [
        { p: "After logging in, press <b>My profile</b> on the exam list." },
        { img: "student/06-profile.png", size: "side", caption: "My profile", legend: [
          "Your name, roll number, batch and (partly hidden) email.",
          "<b>Change password</b>: type your current password, then your new one twice (at least 8 characters, different from the old one, and not your roll number).",
          "Back to your exams.",
        ] },
        { ul: [
          "Five wrong current passwords lock this form for 15 minutes.",
          "<b>Log out</b> (on the exam list) ends your session. Do this on shared computers.",
        ] },
      ],
    },
    {
      title: "Rules and your privacy",
      blocks: [
        { h: "The rules in short" },
        { ul: [
          "Take the exam yourself, on one screen, in the exam window.",
          "No copying and pasting, no other websites or apps during the written part, no screen-sharing, remote or recording tools.",
          "Do not share your password.",
          "Report problems to your teacher straight away.",
        ] },
        { h: "What the app collects" },
        { table: { head: ["It records", "When"], rows: [
          ["A screenshot of your screen", "When you leave the exam window in the written part; about every minute in the practical part"],
          ["Webcam photos", "At random times, only if your teacher turned the webcam on for the exam"],
          ["Events: switching away, blocked actions, restarts, connection lost, when you start and finish", "Throughout the exam"],
          ["The <b>names</b> of screen-sharing, remote-access or recording apps", "Only if one is found running"],
        ] } },
        { h: "What it does not collect" },
        { ul: ["Anything you type (no keystroke recording)", "Sound from your microphone", "Your files, messages or browsing history", "Anything before or after the exam"] },
        { p: "Your teacher and the administrator can see the evidence for your exam. Screenshots and photos are deleted by your school after a retention period; the event log and marks are kept." },
      ],
    },
    {
      title: "Quick guide in Bangla (সংক্ষিপ্ত নির্দেশিকা)",
      newPage: true,
      blocks: [
        { html: `<div class="bn">
<p><b>পরীক্ষার আগের দিন:</b> অ্যাপ ইনস্টল করুন, লগইন করে দেখুন সব ঠিক আছে কি না।</p>
<h3>ইনস্টল (Mac)</h3>
<ol>
<li>শিক্ষকের দেওয়া লিংক থেকে <code>.dmg</code> ফাইল নামান, খুলুন এবং <b>ExamProctor</b> কে <b>Applications</b> ফোল্ডারে টেনে দিন।</li>
<li>অ্যাপ খুললে Mac বলতে পারে যাচাই করা যায়নি: <b>System Settings → Privacy &amp; Security</b> এ গিয়ে <b>Open Anyway</b> চাপুন (macOS 14 বা পুরনো হলে অ্যাপে রাইট ক্লিক করে <b>Open</b>)।</li>
<li><b>Privacy &amp; Security → Screen &amp; System Audio Recording</b> এ ExamProctor চালু করুন (পরীক্ষায় ক্যামেরা লাগলে <b>Camera</b> ও চালু করুন), তারপর অ্যাপ বন্ধ করে আবার খুলুন।</li>
</ol>
<h3>লগইন</h3>
<ul>
<li><b>Start Exam</b> চাপুন, তারপর রোল নম্বর ও পাসওয়ার্ড দিন।</li>
<li>প্রথমবার হলে: শিক্ষক কাগজে পাসওয়ার্ড দেবেন, অথবা <b>First time? Activate account</b> চেপে রোল নম্বর ও নিবন্ধিত ইমেইল দিন; পাসওয়ার্ড ইমেইলে আসবে।</li>
<li>পাসওয়ার্ড গোপন রাখুন। <b>My profile</b> থেকে বদলাতে পারবেন।</li>
</ul>
<h3>পরীক্ষা শুরুর আগে</h3>
<ul>
<li>একটাই মনিটর রাখুন। স্ক্রিন শেয়ার, রিমোট অ্যাক্সেস ও রেকর্ডিং অ্যাপ (OBS, TeamViewer, AnyDesk, Parsec ইত্যাদি) বন্ধ করুন।</li>
<li>চার্জার লাগান এবং ইন্টারনেট ঠিক আছে কি না দেখুন।</li>
<li>তালিকা থেকে পরীক্ষা বেছে <b>Begin exam</b> চাপুন।</li>
</ul>
<h3>লিখিত অংশ</h3>
<ul>
<li>ফুল-স্ক্রিনে Google Form খুলবে। কপি-পেস্ট, ডেভেলপার টুলস, অন্য ওয়েবসাইট বা অন্য অ্যাপে যাওয়া বন্ধ বা রেকর্ড হয়।</li>
<li>পরীক্ষার উইন্ডো ছেড়ে গেলে স্ক্রিনশট নেওয়া হয় এবং শিক্ষক জানতে পারেন। ফিরে এলে প্রশ্ন আসবে: <b>Return to exam</b> চাপুন। <b>Quit exam</b> চাপলে পরীক্ষা শেষ এবং <b>০ নম্বর</b> দেওয়া হবে।</li>
<li>ফর্ম <b>Submit</b> করার পর প্র্যাকটিক্যাল থাকলে <b>Start practical part</b> চাপুন।</li>
</ul>
<h3>প্র্যাকটিক্যাল অংশ</h3>
<ul>
<li>ছোট উইন্ডোতে সময় ও নির্দেশনা দেখাবে। নিজের অ্যাপে কাজ করুন, এক অ্যাপ থেকে অন্য অ্যাপে যেতে পারবেন।</li>
<li>প্রায় প্রতি মিনিটে স্ক্রিনশট নেওয়া হয়। কাজ শেষে <b>Finish practical</b> চাপুন।</li>
</ul>
<h3>সমস্যা হলে</h3>
<ul>
<li><b>ইন্টারনেট চলে গেলে:</b> উইন্ডো খোলা রাখুন, আবার সংযোগ হলে অ্যাপ নিজেই সব পাঠিয়ে দেবে।</li>
<li><b>কম্পিউটার বন্ধ বা অ্যাপ ক্র্যাশ করলে:</b> আবার লগইন করে <b>Begin exam</b> চাপুন, একই জায়গা থেকে শুরু হবে। শিক্ষককে জানান, সময় যোগ করে দিতে পারেন।</li>
<li><b>পাসওয়ার্ড ভুলে গেলে:</b> শিক্ষকের কাছ থেকে নতুন পাসওয়ার্ড নিন।</li>
<li><b>ভুলে Quit চাপলে:</b> সঙ্গে সঙ্গে শিক্ষককে বলুন। তিনি অনুমতি না দিলে আর ঢোকা যাবে না।</li>
<li>সময় শেষ হওয়ার <b>আগেই</b> ফর্ম জমা দিন।</li>
</ul>
</div>` },
      ],
    },
  ],
};
