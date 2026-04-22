export interface AtlasTask {
    id: string;
    label: string;
    prompt: string;
}

export interface AtlasTaskCategory {
    name: string;
    tasks: AtlasTask[];
}

export const ATLAS_TASK_CATEGORIES: AtlasTaskCategory[] = [
    {
        name: 'AP Classroom',
        tasks: [
            {
                id: 'ap-01',
                label: 'Open AP Classroom',
                prompt: 'Go to AP Classroom at myap.collegeboard.org, sign in, and show me my list of AP courses.',
            },
            {
                id: 'ap-02',
                label: 'Open a specific AP class',
                prompt: 'Go to AP Classroom, sign in, find my AP Computer Science Principles course, and open it so I can see the units.',
            },
            {
                id: 'ap-03',
                label: 'Find latest progress check',
                prompt: 'Go to AP Classroom, sign in, open my AP Calculus AB class, and find the most recent progress check assignment.',
            },
            {
                id: 'ap-04',
                label: 'Open Unit progress check',
                prompt: 'Go to AP Classroom, sign in, open my AP Chemistry class, navigate to the Unit on Chemical Bonding, and open the progress check for that unit.',
            },
            {
                id: 'ap-05',
                label: 'Find AP practice test PDF',
                prompt: 'Go to AP Classroom, sign in, open any of my AP courses, and find a downloadable practice exam PDF.',
            },
            {
                id: 'ap-06',
                label: 'Open AP English assignment',
                prompt: 'Go to AP Classroom, sign in, open my AP English Literature class, find the most recent assignment, and read its instructions.',
            },
            {
                id: 'ap-07',
                label: 'Check AP Computer Science A progress check',
                prompt: 'Go to AP Classroom, sign in, open AP Computer Science A, navigate to Unit 1, open the progress check, and check how many questions it contains.',
            },
            {
                id: 'ap-08',
                label: 'Browse AP exam resources',
                prompt: 'Go to the College Board AP Classroom site, sign in, and find the exam resources or past free response questions section for any AP course I am enrolled in.',
            },
        ],
    },
    {
        name: 'Google Docs',
        tasks: [
            {
                id: 'gdoc-01',
                label: 'Create new doc and type a paragraph',
                prompt: 'Open Google Docs, create a new blank document, give it the title "My Notes", and type a short introductory paragraph in the body.',
            },
            {
                id: 'gdoc-02',
                label: 'Create essay draft with heading',
                prompt: 'Open Google Docs, create a new document titled "Essay Draft", apply the Heading 1 style to write "Introduction", then type two sentences in the body below it.',
            },
            {
                id: 'gdoc-03',
                label: 'Find and replace in a doc',
                prompt: 'Open Google Docs, open the most recent document in my drive, use Find & Replace (Ctrl+H) to find the word "the" and replace the first occurrence with "THE".',
            },
            {
                id: 'gdoc-04',
                label: 'Add a table to a doc',
                prompt: 'Open Google Docs, create a new document titled "Schedule", insert a 3-column 4-row table, and fill in the header row with "Day", "Time", "Task".',
            },
            {
                id: 'gdoc-05',
                label: 'Use Explore feature',
                prompt: 'Open Google Docs, open any existing document in my drive, click the Explore button in the bottom-right corner, and search for information related to the document topic.',
            },
            {
                id: 'gdoc-06',
                label: 'Insert bullet list',
                prompt: 'Open Google Docs, create a new document titled "To Do List", add a bulleted list with five items: Homework, Study, Exercise, Read, Sleep.',
            },
        ],
    },
    {
        name: 'Google Sheets',
        tasks: [
            {
                id: 'gsheet-01',
                label: 'Create spreadsheet with data',
                prompt: 'Open Google Sheets, create a new spreadsheet, add headers in row 1: Name, Subject, Score, Grade. Fill in 5 rows of sample student data.',
            },
            {
                id: 'gsheet-02',
                label: 'Monthly expenses tracker',
                prompt: 'Open Google Sheets, create a new spreadsheet titled "Monthly Expenses", add expense categories in column A (Rent, Food, Transport, Utilities, Entertainment), add sample dollar amounts in column B, and use SUM in B7 to total them.',
            },
            {
                id: 'gsheet-03',
                label: 'Create chart from data',
                prompt: 'Open Google Sheets, create a spreadsheet with months Jan-Jun in column A and sales numbers in column B, then select the data and insert a bar chart.',
            },
            {
                id: 'gsheet-04',
                label: 'Use VLOOKUP formula',
                prompt: 'Open Google Sheets, create a new spreadsheet with student names in column A and grades in column B, then in column D write a VLOOKUP formula that looks up a name from D1.',
            },
            {
                id: 'gsheet-05',
                label: 'Conditional formatting',
                prompt: 'Open Google Sheets, create a spreadsheet with test scores 55, 72, 88, 91, 45, 67 in column A, then apply conditional formatting to highlight scores below 60 in red and above 85 in green.',
            },
        ],
    },
    {
        name: 'Google Drive',
        tasks: [
            {
                id: 'gdrive-01',
                label: 'Create folder and doc inside it',
                prompt: 'Open Google Drive, create a new folder called "AP Exam Prep", navigate into it, then create a new Google Doc inside it titled "Study Schedule".',
            },
            {
                id: 'gdrive-02',
                label: 'Search for a file',
                prompt: 'Open Google Drive and use the search bar to find any files with "homework" in the name. Show me the results.',
            },
            {
                id: 'gdrive-03',
                label: 'Check Shared with Me',
                prompt: 'Open Google Drive, navigate to the "Shared with me" section, and find the most recently shared file or folder.',
            },
            {
                id: 'gdrive-04',
                label: 'Upload a file',
                prompt: 'Open Google Drive and navigate to the "New" button to see the options for uploading a file or creating new content.',
            },
        ],
    },
    {
        name: 'Khan Academy',
        tasks: [
            {
                id: 'khan-01',
                label: 'Find calculus derivatives lesson',
                prompt: 'Open Khan Academy, search for "derivatives calculus", navigate to the relevant course, and start the first lesson or exercise.',
            },
            {
                id: 'khan-02',
                label: 'AP Statistics inference unit',
                prompt: 'Open Khan Academy, find the AP Statistics course, navigate to the unit on inference for categorical data, and open the first video in that unit.',
            },
            {
                id: 'khan-03',
                label: 'SAT Math practice',
                prompt: 'Open Khan Academy, navigate to the SAT preparation section, find the Math practice area, and start a practice problem set.',
            },
            {
                id: 'khan-04',
                label: 'AP Physics C course',
                prompt: 'Open Khan Academy, find the AP Physics C: Mechanics course, navigate to the unit on kinematics, and open the first lesson.',
            },
            {
                id: 'khan-05',
                label: 'Algebra 2 skills challenge',
                prompt: 'Open Khan Academy, navigate to the Algebra 2 course, find a skills challenge or unit test, and begin it.',
            },
            {
                id: 'khan-06',
                label: 'SAT diagnostic test intro',
                prompt: 'Open Khan Academy, go to the SAT preparation section, find the full-length practice test or diagnostic test, and navigate to the start screen.',
            },
        ],
    },
    {
        name: 'GitHub',
        tasks: [
            {
                id: 'gh-01',
                label: 'Find qwen2.5 repositories',
                prompt: 'Open GitHub, search for repositories related to "qwen2.5" model, open the top result, and scroll through the README.',
            },
            {
                id: 'gh-02',
                label: 'Browse trending Python repos',
                prompt: 'Open GitHub, navigate to the Trending page, filter by Python language, and show me the top trending Python repository today.',
            },
            {
                id: 'gh-03',
                label: 'Find good first issues',
                prompt: 'Open GitHub, navigate to the "ollama" repository by ollama/ollama, go to the Issues tab, filter by the "good first issue" label, and read the first result.',
            },
            {
                id: 'gh-04',
                label: 'Check TensorFlow latest release',
                prompt: 'Open GitHub, search for the tensorflow/tensorflow repository, navigate to the Releases page, and read the changelog for the most recent release.',
            },
            {
                id: 'gh-05',
                label: 'Check GitHub Actions run',
                prompt: 'Open GitHub, navigate to any popular open source repository like facebook/react, go to the Actions tab, and show me the most recent workflow run and its status.',
            },
            {
                id: 'gh-06',
                label: 'Browse Ollama issues',
                prompt: 'Open GitHub, navigate to the ollama/ollama repository, go to the Issues tab, sort by most recently updated, and read the first open issue.',
            },
        ],
    },
    {
        name: 'Research & Search',
        tasks: [
            {
                id: 'search-01',
                label: 'AP exam study tips',
                prompt: 'Search Google for "best strategies for studying AP exams" and open the first result. Read the main tips listed on the page.',
            },
            {
                id: 'search-02',
                label: 'Python list comprehension tutorial',
                prompt: 'Search Google for "Python list comprehension examples" and find a page with clear code examples. Navigate to it and read the first example.',
            },
            {
                id: 'search-03',
                label: 'Wikipedia: Machine Learning',
                prompt: 'Open Wikipedia and search for "Machine Learning". On the article page, navigate to the section about Neural Networks and read the first paragraph.',
            },
            {
                id: 'search-04',
                label: 'Wikipedia: Photosynthesis',
                prompt: 'Open Wikipedia, look up "Photosynthesis", find the Light-dependent reactions section, and locate the chemical equation shown there.',
            },
            {
                id: 'search-05',
                label: 'Wikipedia: French Revolution causes',
                prompt: 'Open Wikipedia, search for "French Revolution", navigate to the Causes section, and read the main factors listed.',
            },
            {
                id: 'search-06',
                label: 'Google Scholar AI papers',
                prompt: 'Open Google Scholar at scholar.google.com, search for "large language models 2024", and list the titles of the first three results.',
            },
            {
                id: 'search-07',
                label: 'Apple stock price',
                prompt: 'Search Google for "Apple AAPL stock price" and read the current or most recent price shown in the search results.',
            },
            {
                id: 'search-08',
                label: 'ACT vs SAT comparison',
                prompt: 'Search Google for "ACT vs SAT which is better 2024", open the first article, and summarize the key differences it describes.',
            },
            {
                id: 'search-09',
                label: 'WolframAlpha derivative',
                prompt: 'Open WolframAlpha at wolframalpha.com, compute the derivative of x^3 + 2x^2 - 5x + 1, and read the result.',
            },
            {
                id: 'search-10',
                label: 'WolframAlpha system of equations',
                prompt: 'Open WolframAlpha, enter the system of equations "2x + y = 5, x - y = 1" and find the solution for x and y.',
            },
        ],
    },
    {
        name: 'YouTube',
        tasks: [
            {
                id: 'yt-01',
                label: 'Find calculus tutorial',
                prompt: 'Open YouTube, search for "calculus derivatives tutorial", and open the video with the most views. Read its title and the channel name.',
            },
            {
                id: 'yt-02',
                label: 'AP Chemistry review video',
                prompt: 'Open YouTube, search for "AP Chemistry full review 2024", filter results by videos uploaded this year, and open the first result.',
            },
            {
                id: 'yt-03',
                label: 'Binary search algorithm tutorial',
                prompt: 'Open YouTube, search for "binary search algorithm explained", find a video longer than 10 minutes, open it, and read the video description.',
            },
            {
                id: 'yt-04',
                label: 'AP Physics exam prep',
                prompt: 'Open YouTube, search for "AP Physics 1 exam prep 2024", find a video longer than 20 minutes, and check its view count and upload date.',
            },
            {
                id: 'yt-05',
                label: 'Lo-fi study music playlist',
                prompt: 'Open YouTube, search for "lo-fi hip hop study music playlist", open the first playlist result, and show me the first few tracks listed.',
            },
        ],
    },
    {
        name: 'Reddit',
        tasks: [
            {
                id: 'reddit-01',
                label: 'AP exam tips on r/apstudents',
                prompt: 'Open Reddit, navigate to the r/apstudents subreddit, search for posts about "AP Calc exam tips", open the top result, and read the highest-voted comment.',
            },
            {
                id: 'reddit-02',
                label: 'Top Python learning post',
                prompt: 'Open Reddit, navigate to r/learnprogramming, filter by top posts of this week, and read the title and first comment of the top post.',
            },
            {
                id: 'reddit-03',
                label: 'Browse r/worldnews top stories',
                prompt: 'Open Reddit, navigate to r/worldnews, sort by top posts of this week, and list the titles of the first five posts.',
            },
            {
                id: 'reddit-04',
                label: 'r/MachineLearning top paper',
                prompt: 'Open Reddit, navigate to r/MachineLearning, sort by hot, and open the most upvoted post. Read its title and main text.',
            },
        ],
    },
    {
        name: 'Amazon',
        tasks: [
            {
                id: 'amz-01',
                label: 'Search mechanical keyboards',
                prompt: 'Open Amazon, search for "mechanical keyboard under $100", sort results by Average Customer Review, and note the name and price of the top result.',
            },
            {
                id: 'amz-02',
                label: 'Find AirPods Pro price',
                prompt: 'Open Amazon, search for "AirPods Pro", find the official Apple listing, and read the current price and number of customer reviews.',
            },
            {
                id: 'amz-03',
                label: 'Best-selling books',
                prompt: 'Open Amazon, navigate to the Books department, find the Best Sellers list, and list the top 3 best-selling books with their authors.',
            },
            {
                id: 'amz-04',
                label: 'TI-84 graphing calculator',
                prompt: 'Open Amazon, search for "TI-84 Plus graphing calculator", find the main listing, and read the price, star rating, and number of reviews.',
            },
            {
                id: 'amz-05',
                label: 'Compare laptop deals',
                prompt: 'Open Amazon, search for "laptop under $500 student", sort by Best Sellers Rank, and compare the top two results by price, RAM, and storage.',
            },
        ],
    },
    {
        name: 'Productivity Tools',
        tasks: [
            {
                id: 'prod-01',
                label: 'Google Translate paragraph',
                prompt: 'Open Google Translate, set the source language to English and target to Spanish, and translate the sentence: "Education is the most powerful weapon you can use to change the world."',
            },
            {
                id: 'prod-02',
                label: 'DeepL translate and back-translate',
                prompt: 'Open DeepL at deepl.com, translate this paragraph from English to French: "Studying for AP exams requires consistent effort and practice. Make a schedule and stick to it." Then translate the French result back to English to check accuracy.',
            },
            {
                id: 'prod-03',
                label: 'Google Calendar event',
                prompt: 'Open Google Calendar, navigate to tomorrow\'s date, and create a new event called "Study Session" from 7:00 PM to 9:00 PM.',
            },
            {
                id: 'prod-04',
                label: 'Google Calendar recurring event',
                prompt: 'Open Google Calendar, create a new recurring weekly event called "AP Review" every Sunday at 2:00 PM, set it to repeat for 10 weeks.',
            },
            {
                id: 'prod-05',
                label: 'Google Keep checklist',
                prompt: 'Open Google Keep at keep.google.com, create a new note, give it the title "Exam Prep", and add a checklist with items: Review notes, Practice problems, Watch review video, Take mock test.',
            },
            {
                id: 'prod-06',
                label: 'Google Forms quiz',
                prompt: 'Open Google Forms, create a new blank form titled "Chapter 1 Quiz", add a multiple choice question asking "What is the powerhouse of the cell?" with options Nucleus, Mitochondria, Ribosome, Golgi apparatus.',
            },
            {
                id: 'prod-07',
                label: 'Google Forms 3-question quiz',
                prompt: 'Open Google Forms, create a quiz titled "AP Biology Quiz" with three questions: one multiple choice, one short answer, and one checkbox question. Mark it as a quiz in settings.',
            },
            {
                id: 'prod-08',
                label: 'Google Slides 5-slide presentation',
                prompt: 'Open Google Slides, create a new presentation titled "Study Strategies", apply a consistent theme, and add 5 slides: Title, Introduction, Tip 1, Tip 2, Conclusion. Add a heading to each slide.',
            },
            {
                id: 'prod-09',
                label: 'Google Maps directions',
                prompt: 'Open Google Maps, search for directions from Times Square New York to Central Park, and note the walking time and distance.',
            },
            {
                id: 'prod-10',
                label: 'Trello study board',
                prompt: 'Open Trello at trello.com, create a new board called "AP Exam Study Plan", add three lists: "To Study", "Studying", "Mastered", and add two cards to "To Study": "Unit 1 Review" and "Practice FRQ".',
            },
        ],
    },
    {
        name: 'Developer Tools',
        tasks: [
            {
                id: 'dev-01',
                label: 'MDN Array.map docs',
                prompt: 'Open MDN Web Docs at developer.mozilla.org, search for "Array.prototype.map", open the documentation page, and read the Syntax section.',
            },
            {
                id: 'dev-02',
                label: 'Stack Overflow React useState',
                prompt: 'Open Stack Overflow, search for "React useState hook with objects", open the question with the highest score, and read the accepted answer.',
            },
            {
                id: 'dev-03',
                label: 'npm axios package info',
                prompt: 'Open the npm website at npmjs.com, search for the "axios" package, open its page, and read its weekly download count and latest version number.',
            },
            {
                id: 'dev-04',
                label: 'Google Fonts Roboto import',
                prompt: 'Open Google Fonts at fonts.google.com, search for the "Roboto" font, select Regular 400 and Bold 700 weights, and find the CSS import link to copy.',
            },
            {
                id: 'dev-05',
                label: 'CodePen color button',
                prompt: 'Open CodePen at codepen.io, create a new pen, write HTML for a button that says "Click Me", add CSS to style it blue, and add JavaScript so clicking it changes the background color randomly.',
            },
        ],
    },
    {
        name: 'News & Media',
        tasks: [
            {
                id: 'news-01',
                label: 'BBC Tech headlines',
                prompt: 'Open BBC News at bbc.com/news, navigate to the Technology section, and list the titles of the first three articles.',
            },
            {
                id: 'news-02',
                label: 'Hacker News top story',
                prompt: 'Open Hacker News at news.ycombinator.com, find the number one story today, and read its title, score, and number of comments.',
            },
            {
                id: 'news-03',
                label: 'NYT Science section',
                prompt: 'Open The New York Times at nytimes.com, navigate to the Science section, and read the headline and subheadline of the top story.',
            },
            {
                id: 'news-04',
                label: 'LinkedIn internship search',
                prompt: 'Open LinkedIn at linkedin.com, search for "software engineer internship summer 2025", and read the title, company, and location of the first three job postings.',
            },
        ],
    },
    {
        name: 'Advanced Multi-Step',
        tasks: [
            {
                id: 'adv-01',
                label: 'Google Drive folder → nested doc',
                prompt: 'Open Google Drive, create a new folder called "AP Exam Prep 2025", open the folder, create a Google Doc inside it titled "AP Calc Notes", and in that doc write the heading "Chapter 1: Limits" and two bullet points underneath.',
            },
            {
                id: 'adv-02',
                label: 'Quizlet AP Bio flashcards',
                prompt: 'Open Quizlet at quizlet.com, search for "AP Biology Cell Division flashcards", open the set with the most stars or most users, and flip through the first five cards reading both the term and definition sides.',
            },
            {
                id: 'adv-03',
                label: 'Quizlet AP US History Chapter 1',
                prompt: 'Open Quizlet, search for "AP US History Chapter 1", find a flashcard set with more than 50 cards, open it, and flip through the first 3 cards.',
            },
            {
                id: 'adv-04',
                label: 'Google Sheets grade tracker with chart',
                prompt: 'Open Google Sheets, create a new spreadsheet titled "Grade Tracker", add columns: Subject, Q1, Q2, Q3, Q4. Fill in five subjects with sample grades. Add a row for averages using AVERAGE formula. Then insert a column chart showing Q1 grades.',
            },
            {
                id: 'adv-05',
                label: 'Reddit → Stack Overflow deep research',
                prompt: 'Go to Reddit r/learnprogramming, find a post asking a Python question. Then open a new tab, go to Stack Overflow, and search for the same Python question to find a more detailed answer.',
            },
            {
                id: 'adv-06',
                label: 'Google → Wikipedia deep dive',
                prompt: 'Search Google for "how does CRISPR gene editing work", open the top result, read the main explanation, then open Wikipedia and find the CRISPR article to compare the explanation in the Mechanism section.',
            },
            {
                id: 'adv-07',
                label: 'Notion book reading list',
                prompt: 'Open Notion at notion.so, create a new page titled "Reading List", convert it to a table database, add columns for Title, Author, Status (select), and Rating. Add 3 book entries.',
            },
            {
                id: 'adv-08',
                label: 'AP Classroom → Khan Academy cross-reference',
                prompt: 'Go to AP Classroom and find out which unit my AP Calculus class is currently on. Then go to Khan Academy and find the equivalent unit in their AP Calculus AB course, and open the first video.',
            },
            {
                id: 'adv-09',
                label: 'GitHub repo → npm package check',
                prompt: 'Open GitHub, navigate to the "axios" repository, check the latest release version. Then open npmjs.com, search for axios, and confirm the npm latest version matches the GitHub release.',
            },
            {
                id: 'adv-10',
                label: 'Wolfram + Google Docs calculation log',
                prompt: 'Open WolframAlpha, compute the integral of sin(x)cos(x) from 0 to pi. Note the result. Then open Google Docs, create a new document titled "Math Solutions", and type the integral and its answer as the first entry.',
            },
        ],
    },
    {
        name: 'Quizlet & Flashcards',
        tasks: [
            {
                id: 'quiz-01',
                label: 'AP Biology flashcard set',
                prompt: 'Open Quizlet, search for "AP Biology Cell Structure", open the most popular flashcard set, and flip through the first 5 cards reading both sides.',
            },
            {
                id: 'quiz-02',
                label: 'Create custom flashcard set',
                prompt: 'Open Quizlet, create a new study set titled "AP Vocabulary", add 5 terms: Mitosis, Meiosis, Osmosis, Diffusion, Homeostasis — with a one-sentence definition for each.',
            },
            {
                id: 'quiz-03',
                label: 'AP Government flashcards',
                prompt: 'Open Quizlet, search for "AP Government and Politics key terms", open a set with more than 30 cards, and start a Learn session.',
            },
        ],
    },
    {
        name: 'College Board',
        tasks: [
            {
                id: 'cb-01',
                label: 'College Board SAT registration',
                prompt: 'Go to the College Board website at collegeboard.org, navigate to the SAT section, and find the page for SAT registration — note the next available test date.',
            },
            {
                id: 'cb-02',
                label: 'Check AP score release date',
                prompt: 'Go to the College Board website, find the AP Scores section, and read the information about when AP scores are released and how to access them.',
            },
            {
                id: 'cb-03',
                label: 'Find AP free response questions',
                prompt: 'Go to the College Board website, navigate to AP Exams, find the free response questions archive for AP Calculus AB, and open the most recent year available.',
            },
            {
                id: 'cb-04',
                label: 'BigFuture college search',
                prompt: 'Go to the College Board BigFuture website, search for colleges that offer Computer Science programs with small class sizes, and read the top three results.',
            },
        ],
    },
    {
        name: 'Gmail',
        tasks: [
            {
                id: 'gmail-01',
                label: 'Compose a study reminder email',
                prompt: 'Open Gmail, compose a new email to yourself with the subject "AP Exam Study Reminder", and in the body write a brief study schedule for the week.',
            },
            {
                id: 'gmail-02',
                label: 'Search inbox for important emails',
                prompt: 'Open Gmail, use the search bar to find all emails with "assignment" in the subject, and list the sender and subject of the first three results.',
            },
            {
                id: 'gmail-03',
                label: 'Create an email draft',
                prompt: 'Open Gmail, compose a new draft email to a teacher asking for extra help on AP Chemistry Unit 3. Write a polite three-sentence message and save it as a draft.',
            },
            {
                id: 'gmail-04',
                label: 'Label and organize emails',
                prompt: 'Open Gmail, find all emails from the past week, open the most recent unread email, mark it as important, and move it to the Primary inbox if it is in another tab.',
            },
            {
                id: 'gmail-05',
                label: 'Set up email signature',
                prompt: 'Open Gmail, go to Settings, navigate to the Signature section, and create a new signature with your name and the line "AP Student | Class of 2026".',
            },
        ],
    },
];

export const ALL_ATLAS_TASKS: AtlasTask[] = ATLAS_TASK_CATEGORIES.flatMap(c => c.tasks);
