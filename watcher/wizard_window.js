// Combo Watcher setup window: a native macOS window showing the local setup page.
// Run: osascript -l JavaScript wizard_window.js URL [ICON.icns]
ObjC.import('Cocoa');
ObjC.import('WebKit');

function run(argv) {
  var url = argv[0], icon = argv[1] || '';
  var app = $.NSApplication.sharedApplication;
  app.setActivationPolicy(0);                                   // a regular app with a Dock icon
  if (icon) {
    var img = $.NSImage.alloc.initWithContentsOfFile(icon);
    if (img && !img.isNil()) app.applicationIconImage = img;
  }

  // Menu bar: Quit plus the Edit menu, so Cmd-C / Cmd-V / Cmd-A work in the text fields
  var bar = $.NSMenu.alloc.init;
  var appItem = $.NSMenuItem.alloc.init;
  bar.addItem(appItem);
  var appMenu = $.NSMenu.alloc.init;
  appMenu.addItemWithTitleActionKeyEquivalent('Quit Combo Watcher', 'terminate:', 'q');
  appItem.submenu = appMenu;
  var editItem = $.NSMenuItem.alloc.init;
  bar.addItem(editItem);
  var edit = $.NSMenu.alloc.initWithTitle('Edit');
  [['Undo', 'undo:', 'z'], ['Cut', 'cut:', 'x'], ['Copy', 'copy:', 'c'], ['Paste', 'paste:', 'v'],
   ['Select All', 'selectAll:', 'a']].forEach(function (m) {
    edit.addItemWithTitleActionKeyEquivalent(m[0], m[1], m[2]);
  });
  editItem.submenu = edit;
  app.mainMenu = bar;

  ObjC.registerSubclass({
    name: 'CWWindowDelegate',
    protocols: ['NSWindowDelegate'],
    methods: {
      'windowWillClose:': {
        types: ['void', ['id']],
        implementation: function (note) { $.NSApplication.sharedApplication.terminate(null); }
      }
    }
  });

  // titled | closable | miniaturizable | full-size content view
  var style = 1 | 2 | 4 | 32768;
  var win = $.NSWindow.alloc.initWithContentRectStyleMaskBackingDefer($.NSMakeRect(0, 0, 900, 640), style, 2, false);
  win.titlebarAppearsTransparent = true;
  win.titleVisibility = 1;                                      // hidden title text
  win.title = 'Combo Watcher';
  win.releasedWhenClosed = false;
  var delegate = $.CWWindowDelegate.alloc.init;
  win.delegate = delegate;

  var config = $.WKWebViewConfiguration.alloc.init;
  var web = $.WKWebView.alloc.initWithFrameConfiguration(win.contentView.bounds, config);
  web.autoresizingMask = 2 | 16;                                // width and height follow the window
  win.contentView.addSubview(web);
  web.loadRequest($.NSURLRequest.requestWithURL($.NSURL.URLWithString(url)));

  win.center;
  win.makeKeyAndOrderFront(null);
  app.activateIgnoringOtherApps(true);
  app.run;
}
