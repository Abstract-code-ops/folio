// All visitor-facing copy for the landing page lives here.
// Edit this file — nothing is hardcoded in the components.

export const landing = {
  nav: {
    topics: "Topics",
    howItWorks: "How it works",
    about: "About",
    signIn: "Sign in",
  },
  hero: {
    headline: "Read with purpose",
    subheadline:
      "A hand-picked shelf of textbooks for learning software engineering and computer science. Read them, ask them questions, and get answers that cite the page.",
    primaryCta: "Browse topics",
    secondaryCta: "Why I built this",
  },
  shelf: {
    // Each "book" is a reason Folio is useful / a problem it solves.
    // `label` = short spine text; `title` + `subtitle` = front-cover copy.
    // `spine` = cloth token 1–8. Copy is placeholder — edit freely.
    books: [
      {
        label: "Read first",
        title: "Read first, ask after",
        subtitle:
          "The book stays primary — the AI helps you understand it, not skip it.",
        spine: 1,
      },
      {
        label: "Citations",
        title: "Answers that cite the page",
        subtitle:
          "Every answer points to the exact section and page it came from.",
        spine: 6,
      },
      {
        label: "Depth",
        title: "From notes to real depth",
        subtitle:
          "Turn thin lecture notes into a working understanding of the textbook.",
        spine: 3,
      },
    ],
  },
  topics: {
    title: "Topics",
    subtitle: "A small shelf, chosen because each pick is worth your time.",
    items: [
      {
        name: "Software engineering",
        blurb: "How systems are designed, structured, and built.",
        count: 2,
      },
      {
        name: "Databases",
        blurb: "How data is stored, queried, and kept consistent.",
        count: 1,
      },
      {
        name: "Programming languages",
        blurb: "The ideas behind the languages we write.",
        count: 1,
      },
      {
        name: "Artificial intelligence",
        blurb: "How machines learn, reason, and generate.",
        count: 0,
      },
    ],
  },
  howItWorks: {
    title: "How it works",
    steps: [
      {
        title: "Pick a topic",
        description:
          "Choose a field you want to actually understand, not just skim.",
      },
      {
        title: "Open a pick",
        description:
          "Read a real textbook in the reader, one section at a time.",
      },
      {
        title: "Ask a question about a page",
        description:
          "Ask anything; get an answer grounded in the text, with a citation that jumps to the page.",
      },
    ],
  },
  closing: {
    sentence:
      "I built Folio so the books worth reading don't stay buried. [Replace with your own words.]",
    cta: "Browse topics",
  },
};
