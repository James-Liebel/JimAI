/**
 * Completion criteria for each Atlas benchmark task.
 *
 * Grading tiers:
 *   pass    — successUrl matches AND successText match (if set) AND agent said "done"
 *   partial — successUrl matches but content indicators not confirmed, OR agent didn't say "done"
 *   fail    — wrong URL, or agent hit max steps, or agent said "cannot"
 */
export interface TaskCriteria {
    /** URL must contain at least one of these substrings when the task finishes. */
    successUrl?: string[];
    /** Page text must contain at least one of these strings to confirm full success. */
    successText?: string[];
    /** Plain-English description of what a completed task looks like. */
    description: string;
    /** Step budget — agent should finish within this many steps. */
    maxSteps: number;
}

export const TASK_CRITERIA: Record<string, TaskCriteria> = {
    // ── AP Classroom ────────────────────────────────────────────────────────
    'ap-01': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['AP', 'course', 'class', 'exam'],
        description: 'Agent is signed in at myap.collegeboard.org and the AP course list is visible.',
        maxSteps: 12,
    },
    'ap-02': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['Computer Science', 'unit', 'progress'],
        description: 'AP Computer Science Principles course is open showing units.',
        maxSteps: 14,
    },
    'ap-03': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['progress check', 'Calculus', 'question'],
        description: 'AP Calculus AB course is open and the most recent progress check is visible.',
        maxSteps: 14,
    },
    'ap-04': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['Chemistry', 'bond', 'progress check'],
        description: 'AP Chemistry Chemical Bonding unit progress check is open.',
        maxSteps: 16,
    },
    'ap-05': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['practice', 'exam', 'pdf', 'download'],
        description: 'A downloadable practice exam PDF is located in any AP course.',
        maxSteps: 14,
    },
    'ap-06': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['English', 'Literature', 'assignment', 'instruction'],
        description: 'AP English Lit assignment instructions are visible.',
        maxSteps: 14,
    },
    'ap-07': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['Computer Science A', 'Unit 1', 'progress check', 'question'],
        description: 'AP Computer Science A Unit 1 progress check is open and question count visible.',
        maxSteps: 16,
    },
    'ap-08': {
        successUrl: ['myap.collegeboard.org'],
        successText: ['free response', 'exam', 'resource'],
        description: 'Exam resources or FRQ section is open in any AP course.',
        maxSteps: 14,
    },

    // ── Google Docs ─────────────────────────────────────────────────────────
    'gdoc-01': {
        successUrl: ['docs.google.com/document'],
        successText: ['My Notes'],
        description: 'A new Google Doc titled "My Notes" is open with a paragraph in the body.',
        maxSteps: 14,
    },
    'gdoc-02': {
        successUrl: ['docs.google.com/document'],
        successText: ['Essay Draft', 'Introduction'],
        description: 'Google Doc "Essay Draft" is open with Heading 1 "Introduction" and body text.',
        maxSteps: 16,
    },
    'gdoc-03': {
        successUrl: ['docs.google.com/document'],
        successText: ['THE'],
        description: 'Find & Replace ran in a Google Doc and replaced "the" with "THE".',
        maxSteps: 14,
    },
    'gdoc-04': {
        successUrl: ['docs.google.com/document'],
        successText: ['Schedule', 'Day', 'Time', 'Task'],
        description: 'Google Doc "Schedule" has a 3-column table with Day/Time/Task headers.',
        maxSteps: 16,
    },
    'gdoc-05': {
        successUrl: ['docs.google.com/document'],
        successText: ['Explore', 'Related'],
        description: 'The Explore sidebar is open in a Google Doc.',
        maxSteps: 12,
    },
    'gdoc-06': {
        successUrl: ['docs.google.com/document'],
        successText: ['To Do List', 'Homework', 'Study'],
        description: 'Google Doc "To Do List" has a bulleted list with all five items.',
        maxSteps: 14,
    },

    // ── Google Sheets ────────────────────────────────────────────────────────
    'gsheet-01': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['Name', 'Subject', 'Score', 'Grade'],
        description: 'Google Sheets spreadsheet is open with headers and 5 rows of student data.',
        maxSteps: 18,
    },
    'gsheet-02': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['Monthly Expenses', 'Rent', 'SUM'],
        description: '"Monthly Expenses" spreadsheet with categories, amounts, and SUM formula.',
        maxSteps: 18,
    },
    'gsheet-03': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['Jan', 'chart', 'Bar'],
        description: 'Spreadsheet with month/sales data and an inserted bar chart.',
        maxSteps: 20,
    },
    'gsheet-04': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['VLOOKUP'],
        description: 'Spreadsheet with a VLOOKUP formula visible in a cell.',
        maxSteps: 16,
    },
    'gsheet-05': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['conditional', 'format', 'green', 'red'],
        description: 'Conditional formatting applied — scores below 60 red, above 85 green.',
        maxSteps: 18,
    },

    // ── Google Drive ─────────────────────────────────────────────────────────
    'gdrive-01': {
        successUrl: ['docs.google.com/document', 'drive.google.com'],
        successText: ['Study Schedule', 'AP Exam Prep'],
        description: '"Study Schedule" doc exists inside "AP Exam Prep" folder in Drive.',
        maxSteps: 16,
    },
    'gdrive-02': {
        successUrl: ['drive.google.com'],
        successText: ['homework'],
        description: 'Google Drive search results showing files with "homework" in the name.',
        maxSteps: 10,
    },
    'gdrive-03': {
        successUrl: ['drive.google.com'],
        successText: ['Shared with me', 'shared'],
        description: '"Shared with me" section is open in Google Drive.',
        maxSteps: 8,
    },
    'gdrive-04': {
        successUrl: ['drive.google.com'],
        successText: ['New', 'Upload', 'Folder', 'Google Docs'],
        description: 'The "New" menu in Google Drive is open showing upload/create options.',
        maxSteps: 8,
    },

    // ── Khan Academy ─────────────────────────────────────────────────────────
    'khan-01': {
        successUrl: ['khanacademy.org'],
        successText: ['derivative', 'calculus', 'exercise', 'lesson'],
        description: 'Khan Academy derivatives/calculus lesson or exercise is open.',
        maxSteps: 12,
    },
    'khan-02': {
        successUrl: ['khanacademy.org'],
        successText: ['AP Statistics', 'inference', 'categorical', 'video'],
        description: 'Khan Academy AP Statistics inference unit video is open.',
        maxSteps: 14,
    },
    'khan-03': {
        successUrl: ['khanacademy.org'],
        successText: ['SAT', 'Math', 'practice', 'problem'],
        description: 'Khan Academy SAT Math practice section is open with a problem.',
        maxSteps: 12,
    },
    'khan-04': {
        successUrl: ['khanacademy.org'],
        successText: ['AP Physics C', 'kinematics', 'lesson'],
        description: 'Khan Academy AP Physics C kinematics lesson is open.',
        maxSteps: 14,
    },
    'khan-05': {
        successUrl: ['khanacademy.org'],
        successText: ['Algebra 2', 'challenge', 'unit test'],
        description: 'Khan Academy Algebra 2 skills challenge or unit test is open.',
        maxSteps: 12,
    },
    'khan-06': {
        successUrl: ['khanacademy.org'],
        successText: ['SAT', 'practice test', 'diagnostic', 'full-length'],
        description: 'Khan Academy SAT diagnostic or full practice test start screen is visible.',
        maxSteps: 12,
    },

    // ── GitHub ───────────────────────────────────────────────────────────────
    'gh-01': {
        successUrl: ['github.com'],
        successText: ['qwen2.5', 'README', 'model'],
        description: 'GitHub search results for qwen2.5 are showing, top repo README is open.',
        maxSteps: 10,
    },
    'gh-02': {
        successUrl: ['github.com/trending'],
        successText: ['Python', 'star', 'trending'],
        description: 'GitHub trending page filtered to Python is showing.',
        maxSteps: 8,
    },
    'gh-03': {
        successUrl: ['github.com'],
        successText: ['good first issue', 'ollama', 'issue'],
        description: 'ollama/ollama Issues filtered by "good first issue" label is open.',
        maxSteps: 10,
    },
    'gh-04': {
        successUrl: ['github.com/tensorflow'],
        successText: ['release', 'changelog', 'tensorflow'],
        description: 'TensorFlow releases page showing latest release changelog.',
        maxSteps: 10,
    },
    'gh-05': {
        successUrl: ['github.com'],
        successText: ['Actions', 'workflow', 'run', 'status'],
        description: 'GitHub Actions tab of a popular repo showing a recent workflow run.',
        maxSteps: 10,
    },
    'gh-06': {
        successUrl: ['github.com/ollama/ollama'],
        successText: ['issue', 'open', 'comment'],
        description: 'ollama/ollama Issues tab open with a recent issue visible.',
        maxSteps: 8,
    },

    // ── Research & Search ────────────────────────────────────────────────────
    'search-01': {
        successUrl: ['google.com', 'collegeboard.org', 'prepscholar.com', 'kaptest.com'],
        successText: ['AP exam', 'study', 'tips', 'strategy'],
        description: 'An article about AP exam study strategies is open.',
        maxSteps: 8,
    },
    'search-02': {
        successUrl: ['google.com', 'python.org', 'w3schools.com', 'realpython.com'],
        successText: ['list comprehension', 'for', 'in'],
        description: 'A page with Python list comprehension code examples is open.',
        maxSteps: 8,
    },
    'search-03': {
        successUrl: ['wikipedia.org/wiki/Machine_learning', 'wikipedia.org'],
        successText: ['machine learning', 'neural network', 'algorithm'],
        description: 'Wikipedia Machine Learning article is open, Neural Networks section visible.',
        maxSteps: 10,
    },
    'search-04': {
        successUrl: ['wikipedia.org/wiki/Photosynthesis', 'wikipedia.org'],
        successText: ['photosynthesis', 'light-dependent', 'chlorophyll'],
        description: 'Wikipedia Photosynthesis article showing the light-dependent reactions section.',
        maxSteps: 10,
    },
    'search-05': {
        successUrl: ['wikipedia.org'],
        successText: ['French Revolution', 'cause', 'monarchy', 'Estates'],
        description: 'Wikipedia French Revolution article is open showing the Causes section.',
        maxSteps: 10,
    },
    'search-06': {
        successUrl: ['scholar.google.com'],
        successText: ['language model', 'paper', 'cite'],
        description: 'Google Scholar search results for "large language models 2024" are showing.',
        maxSteps: 8,
    },
    'search-07': {
        successUrl: ['google.com', 'finance.yahoo.com', 'marketwatch.com'],
        successText: ['AAPL', 'Apple', 'stock', '$'],
        description: 'Apple stock price (AAPL) is visible in search results or a finance page.',
        maxSteps: 6,
    },
    'search-08': {
        successUrl: ['google.com', 'princetonreview.com', 'prepscholar.com'],
        successText: ['ACT', 'SAT', 'difference', 'comparison'],
        description: 'An article comparing ACT and SAT is open.',
        maxSteps: 8,
    },
    'search-09': {
        successUrl: ['wolframalpha.com'],
        successText: ['derivative', 'x^3', 'result', '3x'],
        description: 'WolframAlpha shows the derivative of x^3+2x^2−5x+1 with the result.',
        maxSteps: 8,
    },
    'search-10': {
        successUrl: ['wolframalpha.com'],
        successText: ['solution', 'x =', 'y =', '2'],
        description: 'WolframAlpha shows the solution to the system of equations.',
        maxSteps: 8,
    },

    // ── YouTube ──────────────────────────────────────────────────────────────
    'yt-01': {
        successUrl: ['youtube.com/watch'],
        successText: ['calculus', 'derivative'],
        description: 'A calculus derivatives video is open and playing on YouTube.',
        maxSteps: 10,
    },
    'yt-02': {
        successUrl: ['youtube.com/watch', 'youtube.com/results'],
        successText: ['AP Chemistry', 'review'],
        description: 'YouTube search results or video for AP Chemistry review is showing.',
        maxSteps: 10,
    },
    'yt-03': {
        successUrl: ['youtube.com/watch'],
        successText: ['binary search', 'algorithm', 'description'],
        description: 'A binary search algorithm tutorial longer than 10 minutes is open.',
        maxSteps: 10,
    },
    'yt-04': {
        successUrl: ['youtube.com/watch'],
        successText: ['AP Physics', 'exam', 'prep'],
        description: 'An AP Physics exam prep video is open, view count and date visible.',
        maxSteps: 10,
    },
    'yt-05': {
        successUrl: ['youtube.com/watch', 'youtube.com/playlist'],
        successText: ['lo-fi', 'study', 'music', 'chill'],
        description: 'A lo-fi study music playlist is open on YouTube.',
        maxSteps: 10,
    },

    // ── Reddit ───────────────────────────────────────────────────────────────
    'reddit-01': {
        successUrl: ['reddit.com/r/apstudents', 'reddit.com'],
        successText: ['AP Calc', 'exam', 'tip', 'comment'],
        description: 'r/apstudents post about AP Calc exam tips is open with comments visible.',
        maxSteps: 12,
    },
    'reddit-02': {
        successUrl: ['reddit.com/r/learnprogramming', 'reddit.com'],
        successText: ['Python', 'programming', 'comment'],
        description: 'r/learnprogramming top post is open with comments.',
        maxSteps: 10,
    },
    'reddit-03': {
        successUrl: ['reddit.com/r/worldnews'],
        successText: ['news', 'comment', 'vote'],
        description: 'r/worldnews is open sorted by top posts of the week.',
        maxSteps: 8,
    },
    'reddit-04': {
        successUrl: ['reddit.com/r/MachineLearning'],
        successText: ['machine learning', 'paper', 'model', 'comment'],
        description: 'r/MachineLearning top hot post is open.',
        maxSteps: 10,
    },

    // ── Amazon ───────────────────────────────────────────────────────────────
    'amz-01': {
        successUrl: ['amazon.com'],
        successText: ['mechanical keyboard', 'star', 'rating', '$'],
        description: 'Amazon search for mechanical keyboards sorted by rating, results visible.',
        maxSteps: 10,
    },
    'amz-02': {
        successUrl: ['amazon.com'],
        successText: ['AirPods Pro', '$', 'rating', 'review'],
        description: 'Amazon AirPods Pro listing with price and review count visible.',
        maxSteps: 10,
    },
    'amz-03': {
        successUrl: ['amazon.com/best-sellers', 'amazon.com/bestsellers', 'amazon.com'],
        successText: ['Best Seller', 'book', '#1'],
        description: 'Amazon Best Sellers in Books showing top 3 books with authors.',
        maxSteps: 10,
    },
    'amz-04': {
        successUrl: ['amazon.com'],
        successText: ['TI-84', 'graphing calculator', 'rating', '$'],
        description: 'Amazon TI-84 Plus listing with price, rating, and review count.',
        maxSteps: 10,
    },
    'amz-05': {
        successUrl: ['amazon.com'],
        successText: ['laptop', '$', 'GB', 'RAM'],
        description: 'Amazon laptop search results under $500 showing two comparable listings.',
        maxSteps: 12,
    },

    // ── Productivity Tools ───────────────────────────────────────────────────
    'prod-01': {
        successUrl: ['translate.google.com', 'google.com/translate'],
        successText: ['Educación', 'arma', 'mundo'],
        description: 'Google Translate shows the Spanish translation of the given sentence.',
        maxSteps: 8,
    },
    'prod-02': {
        successUrl: ['deepl.com'],
        successText: ['Für AP-Prüfungen', 'examens AP', 'studying'],
        description: 'DeepL shows the French translation of the study advice paragraph.',
        maxSteps: 10,
    },
    'prod-03': {
        successUrl: ['calendar.google.com'],
        successText: ['Study Session', '7:00 PM', '9:00 PM'],
        description: 'Google Calendar shows a "Study Session" event created for tomorrow 7–9 PM.',
        maxSteps: 14,
    },
    'prod-04': {
        successUrl: ['calendar.google.com'],
        successText: ['AP Review', 'weekly', 'Sunday', 'repeat'],
        description: 'Google Calendar recurring "AP Review" event on Sundays is created.',
        maxSteps: 16,
    },
    'prod-05': {
        successUrl: ['keep.google.com'],
        successText: ['Exam Prep', 'Homework', 'Study', 'Mock test'],
        description: 'Google Keep note "Exam Prep" with all four checklist items is visible.',
        maxSteps: 14,
    },
    'prod-06': {
        successUrl: ['docs.google.com/forms'],
        successText: ['Chapter 1 Quiz', 'Mitochondria', 'multiple choice'],
        description: 'Google Form "Chapter 1 Quiz" with the powerhouse question is created.',
        maxSteps: 16,
    },
    'prod-07': {
        successUrl: ['docs.google.com/forms'],
        successText: ['AP Biology Quiz', 'multiple choice', 'short answer', 'checkbox'],
        description: 'Google Forms quiz with three different question types is created.',
        maxSteps: 18,
    },
    'prod-08': {
        successUrl: ['docs.google.com/presentation'],
        successText: ['Study Strategies', 'Introduction', 'Conclusion'],
        description: 'Google Slides presentation with 5 slides and consistent theme is created.',
        maxSteps: 20,
    },
    'prod-09': {
        successUrl: ['google.com/maps', 'maps.google.com'],
        successText: ['Times Square', 'Central Park', 'walk', 'min'],
        description: 'Google Maps shows walking directions from Times Square to Central Park.',
        maxSteps: 8,
    },
    'prod-10': {
        successUrl: ['trello.com'],
        successText: ['AP Exam Study Plan', 'To Study', 'Studying', 'Mastered'],
        description: 'Trello board "AP Exam Study Plan" with three lists and two cards is created.',
        maxSteps: 18,
    },

    // ── Developer Tools ──────────────────────────────────────────────────────
    'dev-01': {
        successUrl: ['developer.mozilla.org'],
        successText: ['Array.prototype.map', 'Syntax', 'callback', 'Parameters'],
        description: 'MDN Array.prototype.map docs are open with the Syntax section visible.',
        maxSteps: 8,
    },
    'dev-02': {
        successUrl: ['stackoverflow.com'],
        successText: ['useState', 'React', 'object', 'accepted answer'],
        description: 'Stack Overflow question about React useState with objects is open.',
        maxSteps: 10,
    },
    'dev-03': {
        successUrl: ['npmjs.com/package/axios'],
        successText: ['axios', 'weekly downloads', 'version'],
        description: 'npm axios package page showing weekly downloads and latest version.',
        maxSteps: 8,
    },
    'dev-04': {
        successUrl: ['fonts.google.com'],
        successText: ['Roboto', 'import', '@import', 'CSS'],
        description: 'Google Fonts Roboto page with the CSS import link visible.',
        maxSteps: 10,
    },
    'dev-05': {
        successUrl: ['codepen.io'],
        successText: ['Click Me', 'button', 'color'],
        description: 'CodePen has a color-changing button written in HTML/CSS/JS.',
        maxSteps: 20,
    },

    // ── News & Media ─────────────────────────────────────────────────────────
    'news-01': {
        successUrl: ['bbc.com/news', 'bbc.co.uk'],
        successText: ['Technology', 'article', 'news'],
        description: 'BBC News Technology section is open with article headlines visible.',
        maxSteps: 8,
    },
    'news-02': {
        successUrl: ['news.ycombinator.com'],
        successText: ['points', 'comments', 'Ask HN', 'Show HN'],
        description: 'Hacker News front page showing the top story with score and comments.',
        maxSteps: 6,
    },
    'news-03': {
        successUrl: ['nytimes.com'],
        successText: ['Science', 'article', 'headline'],
        description: 'NYT Science section is open with the top story headline visible.',
        maxSteps: 8,
    },
    'news-04': {
        successUrl: ['linkedin.com'],
        successText: ['internship', 'software engineer', 'company', 'location'],
        description: 'LinkedIn job search results for software engineer internships are visible.',
        maxSteps: 10,
    },

    // ── Advanced Multi-Step ──────────────────────────────────────────────────
    'adv-01': {
        successUrl: ['docs.google.com/document'],
        successText: ['AP Exam Prep 2025', 'AP Calc Notes', 'Chapter 1', 'Limits'],
        description: 'Google Doc inside Drive folder has heading and two bullet points.',
        maxSteps: 20,
    },
    'adv-02': {
        successUrl: ['quizlet.com'],
        successText: ['Cell Division', 'term', 'definition', 'flip'],
        description: 'Quizlet AP Biology Cell Division set is open with cards being flipped.',
        maxSteps: 16,
    },
    'adv-03': {
        successUrl: ['quizlet.com'],
        successText: ['AP US History', 'Chapter 1', 'term', 'definition'],
        description: 'Quizlet AP US History Chapter 1 set (50+ cards) is open with 3 cards flipped.',
        maxSteps: 14,
    },
    'adv-04': {
        successUrl: ['docs.google.com/spreadsheets'],
        successText: ['Grade Tracker', 'Subject', 'AVERAGE', 'chart'],
        description: '"Grade Tracker" sheet has 5 subjects, averages, and a column chart.',
        maxSteps: 22,
    },
    'adv-05': {
        successUrl: ['reddit.com', 'stackoverflow.com'],
        successText: ['Python', 'answer', 'comment'],
        description: 'Reddit Python question found; Stack Overflow search for same question done.',
        maxSteps: 18,
    },
    'adv-06': {
        successUrl: ['wikipedia.org'],
        successText: ['CRISPR', 'mechanism', 'Cas9', 'gene'],
        description: 'Wikipedia CRISPR article is open showing the Mechanism section.',
        maxSteps: 14,
    },
    'adv-07': {
        successUrl: ['notion.so'],
        successText: ['Reading List', 'Title', 'Author', 'Status'],
        description: 'Notion database "Reading List" with Title, Author, Status columns and 3 entries.',
        maxSteps: 20,
    },
    'adv-08': {
        successUrl: ['khanacademy.org'],
        successText: ['calculus', 'limit', 'unit', 'video'],
        description: 'Khan Academy Calculus AB unit matching current AP Classroom unit is open.',
        maxSteps: 18,
    },
    'adv-09': {
        successUrl: ['npmjs.com/package/axios'],
        successText: ['axios', 'version', 'weekly'],
        description: 'npm axios page confirms version matches the GitHub release found earlier.',
        maxSteps: 16,
    },
    'adv-10': {
        successUrl: ['docs.google.com/document'],
        successText: ['Math Solutions', 'integral', 'sin', 'cos'],
        description: 'Google Doc "Math Solutions" has the WolframAlpha integral and result typed in.',
        maxSteps: 18,
    },

    // ── Quizlet & Flashcards ─────────────────────────────────────────────────
    'quiz-01': {
        successUrl: ['quizlet.com'],
        successText: ['AP Biology', 'Cell Structure', 'term', 'definition'],
        description: 'Quizlet AP Biology Cell Structure set is open with cards being studied.',
        maxSteps: 12,
    },
    'quiz-02': {
        successUrl: ['quizlet.com'],
        successText: ['AP Vocabulary', 'Mitosis', 'Meiosis', 'Osmosis'],
        description: 'Custom "AP Vocabulary" Quizlet set with 5 biology terms is created.',
        maxSteps: 20,
    },
    'quiz-03': {
        successUrl: ['quizlet.com'],
        successText: ['AP Government', 'Learn', 'term', 'card'],
        description: 'AP Government Quizlet set is open in Learn mode.',
        maxSteps: 12,
    },

    // ── College Board ────────────────────────────────────────────────────────
    'cb-01': {
        successUrl: ['collegeboard.org'],
        successText: ['SAT', 'registration', 'test date', 'register'],
        description: 'College Board SAT registration page showing next test date is open.',
        maxSteps: 10,
    },
    'cb-02': {
        successUrl: ['collegeboard.org'],
        successText: ['AP score', 'release', 'July', 'access'],
        description: 'College Board AP Scores section showing release date information.',
        maxSteps: 10,
    },
    'cb-03': {
        successUrl: ['collegeboard.org', 'apcentral.collegeboard.org'],
        successText: ['Calculus AB', 'free response', 'question', 'exam'],
        description: 'AP Calculus AB free response questions archive is open.',
        maxSteps: 12,
    },
    'cb-04': {
        successUrl: ['bigfuture.collegeboard.org', 'collegeboard.org'],
        successText: ['Computer Science', 'college', 'major', 'program'],
        description: 'BigFuture college search results for CS programs are visible.',
        maxSteps: 12,
    },

    // ── Gmail ────────────────────────────────────────────────────────────────
    'gmail-01': {
        successUrl: ['mail.google.com'],
        successText: ['AP Exam Study Reminder', 'compose', 'send'],
        description: 'Gmail compose window has "AP Exam Study Reminder" subject with body text.',
        maxSteps: 12,
    },
    'gmail-02': {
        successUrl: ['mail.google.com'],
        successText: ['assignment', 'subject', 'inbox', 'from'],
        description: 'Gmail search results for "assignment" emails are showing.',
        maxSteps: 8,
    },
    'gmail-03': {
        successUrl: ['mail.google.com'],
        successText: ['draft', 'Chemistry', 'Unit 3', 'help'],
        description: 'Gmail draft email asking for AP Chemistry Unit 3 help is saved.',
        maxSteps: 14,
    },
    'gmail-04': {
        successUrl: ['mail.google.com'],
        successText: ['important', 'inbox', 'primary'],
        description: 'The most recent unread email is marked important and moved to Primary.',
        maxSteps: 12,
    },
    'gmail-05': {
        successUrl: ['mail.google.com'],
        successText: ['signature', 'AP Student', 'Class of 2026'],
        description: 'Gmail signature with "AP Student | Class of 2026" is saved in Settings.',
        maxSteps: 14,
    },
};
