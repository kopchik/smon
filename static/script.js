"use strict";
var ws = new WebSocket("ws://localhost:8181/stream");


function display_list(list) {
  for (var e of list) {
      var [name, tstamp, [status, out]] = e;
      var check = $("<div/>", {class: "check ok"});
      $("<div/>")
        .addClass("c_name")
        .text(name)
        .appendTo(check);
      $("<div/>")
        .addClass("c_name")
        .text(tstamp)
        .appendTo(check);
      $("<div/>")
        .addClass("out")
        .text(out)
        .appendTo(check);
      check.appendTo("#checks");
      $("#checks").append("<div class='checksep'></div>");

      // $("#checks").append(`
      //   <div class="check ok">
      //     <div class="c_name">${name}</div>
      //     <div class="c_name">${tstamp}</div>
      //     <pre class="out">${out}</pre>
      //   </div>
      // `);

  }
}

ws.onopen = function (event) {
  ws.send("LIST");
}

ws.onmessage = function (event) {
  var list = $.parseJSON(event.data)
  display_list(list);


  ws.send("LIST");
  ws.onmessage = function(event) {
    console.log("NESTED");
  }
}


// function loop() {
//   console.log("test");
//   setTimeout(loop, 3000);
// }
// loop()
//var exampleSocket = new WebSocket("ws://www.example.com/socketserver", "protocolOne");
