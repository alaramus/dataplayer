/** The welcome and its tour (features/onboarding), and the few words of the guide's
    window (features/guide) and of reading aloud (features/speech). */
export const onboarding = {
  title: "Welcome to DataPlayer",
  intro: "Pick a language and how the application looks.",
  tour_offer: "Then take a three-minute tour: you make a small database, work with it and clean it away, with a hint beside every button to press.",
  position: "Step {n} of {total}",
  finish: "Finish",
  next: "Next",
  take_tour: "Take the tour",
  look_around: "Look around myself",
  mark_failed: "The tour could not be marked as seen",
  close_title: "End the tour?",
  close_message: "The tour will not open again by itself. You can take it anytime in Preferences, under Tours.",
  close_confirm: "End tour",
  keep_going: "Keep going",
  end_tour: "End tour",
  more_tours: "See more tours",
  tour: {
    make: {
      title: "Make a database",
      add: "Press + to add a connection.",
      pick: "Choose SQLite.",
      here: "SQLite needs no server: make a database right here, in your own storage.",
      submit: "Keep what is offered, a file with sample data, and make it.",
    },
    open: {
      title: "Open a table",
      connection: "Open the new connection to see its tables.",
      table: "Open the {table} table.",
    },
    filter: {
      title: "Filter the rows",
      open: "Open the filters.",
      fill: "Show only blocked tasks: column status, equals, blocked. Then apply.",
    },
    edit: {
      title: "Change a value",
      cell: "Double-click a task's title to change it.",
      save: "Write a new title and save it. The change goes straight into the database.",
    },
    query: {
      title: "Run a query",
      open: "Open this table as a query: the console gets a SELECT written for it.",
      run: "Run it. Any SQL can be written here.",
    },
    disconnect: {
      title: "Delete the connection",
      edit: "Open the connection's settings.",
      delete: "Delete the connection.",
      confirm: "Confirm. Only the connection goes: the database file stays in your storage.",
    },
    folder: {
      title: "Connect your own folder",
      add: "Press + again.",
      pick: "Choose Files.",
      create: "Create the connection.",
      save: "The path / is the whole of your personal storage. Save the connection.",
    },
    find: {
      title: "Find the file",
      connection: "Open the folder connection.",
      folder: "Open {folder}: the database you made is there.",
    },
    remove: {
      title: "Delete the file",
      tick: "Tick {file}.",
      actions: "Open the actions menu.",
      delete: "Choose Delete.",
      confirm: "Confirm. Nothing of the demonstration is left, and the folder connection stays yours.",
    },
    service: {
      title: "A server, started here",
      add: "Press + once more.",
      pick: "Choose Redis: nothing so far looked like it.",
      start: "This button starts Redis right here, in Docker, with data to try it on, and makes its connection for you. Any server in this catalog with such a button can be started the same way. That is the end of the tour: the window is yours.",
    },
  },
  tours: {
    basics: {
      title: "The basics",
      summary: "Make a database, work with it and clean it away.",
    },
    practice_name: "practice",
    folder_name: "My files",
    preparing: "Making a practice database for this tour…",
    setup_failed: "The tour could not prepare its practice database",
    cleanup_failed: "The tour could not take its practice database away",
    list: {
      take: "Take",
      again: "Again",
    },
    views: {
      title: "A table, read other ways",
      summary: "The same table as a chart, as its structure and as documents.",
      back: "Go back to the {table} tab.",
      open: {
        title: "Open the practice table",
        connection: "This practice database was made for the tour. Open it.",
        table: "Open {table}.",
      },
      chart: {
        title: "As a chart",
        hint: "Draw the page as a chart.",
      },
      structure: {
        title: "As its structure",
        hint: "See the table's columns, keys and indexes.",
      },
      document: {
        title: "As documents",
        hint: "Read the rows as documents rather than a grid.",
      },
      closing: {
        title: "Done",
        text: "The practice database is taken away when you close this.",
      },
    },
    pipeline: {
      title: "A pipeline",
      summary: "Rows of a table saved as a CSV file in your folder.",
      new: {
        title: "A new pipeline",
        space: "Open the pipelines.",
        create: "Make a new pipeline.",
      },
      source: {
        title: "Where rows come from",
        connection: "Press the practice database: its tables open beside the canvas.",
        schema: "Open main, SQLite's one schema.",
        tick: "Tick {table}.",
        done: "Put it on the canvas.",
      },
      target: {
        title: "Where they go",
        connection: "Now press your folder.",
        top: "Tick the folder itself.",
        done: "Put it on the canvas.",
      },
      link: {
        title: "Join them",
        hint: "The hint draws every link that could be made. A row can also be dragged onto another.",
        press: "Press the dashed link from the table to the folder.",
      },
      run: {
        title: "Run it",
        hint: "Run the pipeline. The link saves the table as a CSV file.",
        taken: "The folder already has a file of that name: under “If the name is taken” choose “Keep both”, then Run again.",
      },
      seen: {
        title: "The file",
        space: "Go back to Data.",
        folder: "Open your folder.",
        file: "Here is the CSV the pipeline made. The practice database goes when you finish; the file stays.",
      },
    },
    dashboards: {
      title: "Dashboards",
      summary: "Where dashboards are made and where their metrics come from.",
      space: {
        title: "Dashboards",
        hint: "Open the dashboards.",
      },
      new: {
        title: "A dashboard",
        hint: "A dashboard starts here: charts and tiles of metrics, laid out on a grid.",
        store: "Dashboards keep their metrics in a store an administrator starts once, here.",
      },
      agent: {
        title: "Metrics from an agent",
        open: "Open the sources of metrics.",
        view: "Agents report the machines they run on.",
        register: "Register an agent here: you get its key and a Docker Compose file that starts it on the machine to watch.",
      },
      connections: {
        title: "Metrics from your connections",
        view: "Your connections can report about themselves too.",
        switch: "Choose a connection and switch it on: PostgreSQL, MySQL and Redis report their own metrics.",
      },
    },
    agent: {
      title: "The AI agent",
      summary: "Where the agent's key, model and context are chosen.",
      space: {
        title: "The agent",
        hint: "Open the AI space.",
      },
      chat: {
        title: "A chat",
        hint: "Start a new chat.",
        close: "Close the settings to get back to the chats.",
      },
      key: {
        title: "Its key",
        open: "Open the AI settings.",
        hint: "The default model is chosen here, and beside it the key button: the agent works with your key of a provider, Anthropic, OpenAI and others.",
      },
      model: {
        title: "Its model",
        hint: "Choose the model the chat uses.",
      },
      attach: {
        title: "What it knows",
        hint: "Attach a table, a tab or a node: the agent reads what you mean rather than guessing.",
      },
    },
  },
  guide: {
    title: "Guide",
    not_a_page: "That link does not lead to a page of the guide",
    read_failed: "This page of the guide could not be read",
  },
  speech: {
    listen: "Listen",
    stop: "Stop reading aloud",
    browser_default: "Browser default",
  },
}
