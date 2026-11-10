/** The welcome and its tour (features/onboarding), and the few words of the guide's
    window (features/guide) and of reading aloud (features/speech). */
export const onboarding = {
  title: "Welcome to DataPlayer",
  intro: "Pick a language and how the application looks.",
  tour_offer: "Then take a three-minute tour: you make a small database, work with it and clean it away, with a hint beside every button to press.",
  position: "Step {n} of {total}",
  finish: "Finish",
  take_tour: "Take the tour",
  look_around: "Look around myself",
  mark_failed: "The tour could not be marked as seen",
  close_title: "End the tour?",
  close_message: "The tour will not open again by itself. You can take it anytime in Preferences, under Welcome tour.",
  close_confirm: "End tour",
  keep_going: "Keep going",
  end_tour: "End tour",
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
    finished: {
      title: "You have the basics",
      text: "Connections, tables, filters, edits, queries and your own storage. Pipelines, dashboards and the AI agent are in the bar on the left. The tour is in Preferences whenever you want it again.",
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
