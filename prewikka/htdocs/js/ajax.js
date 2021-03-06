$(document).ready(function(){

  $(document).ajaxStart(function() {
        $("#ajax-spinner").show();
    }).bind("ajaxStop", function() {
        $("#ajax-spinner").hide();
    }).bind("ajaxError", function() {
        $("#ajax-spinner").hide();
    });

  $(document).ajaxError(function( event, xhr, settings, error ) {
       /*
        * If the user aborded the request, this is not an error.
        */
       if ( error == "abort" )
           return;

       if ( ! xhr.responseText )
           prewikka_dialog({message: error || "Unknown AJAX error"});
       else
           prewikka_dialog($.parseJSON(xhr.responseText));
  });

  $(window).on('resize', prewikka_resizeTopMenu);
});


function prewikka_location() {
    return window.history.location || window.location;
}


function _mergedict(obj1, obj2) {
        var obj3 = {};

        for ( var attrname in obj1 ) {
                obj3[attrname] = obj1[attrname];
        }

        for ( var attrname in obj2 ) {
                obj3[attrname] = obj2[attrname];
        }

        return obj3;
}



function __ie_fixes(data)
{
    /*
     * Return if not IE, or IE >= 10
     */
    if ( 'baseURI' in document || window.atob )
        return data;

    var absolute = new RegExp('^(?:[a-z]+:)?//', 'i');

    /*
     * IE9 does not take base url into account for link parameters.
     * Also add the link element to document head to prevent loading problem.
     */
    $(data).filter("link").add($(data).find("link")).each(function() {
        var href = $(this).attr("href");

        if ( href[0] != '/' && ! absolute.test(href) ) {
            var base = document.getElementsByTagName('base')[0];
            $(this).attr("href", base.href + href);
            $('<link rel="stylesheet" href="' + base.href + href +  '" type="text/css" />').appendTo('head');
        }
    });

    return data;
}

function handle_notifications(data)
{
    if ( data.notifications ) {
        $.each(data.notifications, function(_, value) {
            prewikka_notification(value);
        });
    }
}

function prewikka_drawTab(data)
{
    var form;
    var content = __ie_fixes($(data.content));

    handle_notifications(data);

    if ( ! data.content ) {
        if ( ! data.menu )
            return;

        /*
         * If we have a menu, but no content, preserve previous content.
         */
        content = $("#main").html();
    }

    /*
     * Check self and descendant
     */
    form = $(content).closest("form");
    if ( ! form.length )
        form = $(content).find("form");

    if ( ! form.length )
        form = content = content.wrapAll('<form method="get" action="' + prewikka_location().pathname + '"></form>').parent();

    $(form).append(data.menu);
    $("#main").off(); /* clear any events bound to this content by the current view */
    $("#main").html(content);

    prewikka_resizeTopMenu();

    $("#topmenu #help-button").hide();
    $("#timeline #view-settings #main_menu_form").hide();

    $("#config-button").toggle($("#main .prewikka-view-config").length > 0);

    var vh = $("#main .prewikka-view-help");
    if ( vh.length )  {
        $("#topmenu #help-button").show();
        $("#topmenu #help-button").click(function() {
            prewikka_dialog({
                name: "Prelude Help",
                message: $("#main .prewikka-view-help").html()
            });
        });
    }

    $(function () {
        $('[data-toggle="tooltip"]').tooltip();
    });
}

/* Update the tab's menu according to the url */
function _url2menu(url)
{
        var pathname = unescape(url);
        if ( pathname.charAt(0) == "/") pathname = pathname.substr(1);
        if ( pathname.charAt(pathname.length - 1) == "/") pathname = pathname.substr(0, pathname.length - 1);

        var pathtbl = pathname.split("/");
        var wanted = pathtbl.slice(0, 2).join("/");

        var tab = null;
        $("#topmenu .topmenu_item").find("a").each(function() {
                if ( $(this).attr("href").split("?")[0] === wanted ) {
                    tab = $(this);
                    return false;
                }
        });

        if ( tab ) {
                /* Update the document's title according to the names of the section and tab */
                if ( pathtbl[0] != undefined && pathtbl[1] != undefined ) {
                        document.title = $("#prewikka-title").text() + " - " + pathtbl[0].capitalize() + " (" + pathtbl[1].capitalize() + ")";
                }

                /*
                 * Activate div for the selected section
                 */
                $("#menu .menu_item_active").toggleClass("menu_item_inactive", true);
                $("#menu .menu_item_active").toggleClass("menu_item_active", false);
                $("#menu .menu_item_" + pathtbl[0]).toggleClass("menu_item_inactive", false);
                $("#menu .menu_item_" + pathtbl[0]).toggleClass("menu_item_active", true);

                $("#topmenu ul.topmenu_section").hide();
                $("#topmenu_" + pathtbl[0]).show();

                /*
                 * show the tab
                 */
                $("#topmenu .active").toggleClass("active", false);
                $(tab).parents("li").eq(0).toggleClass("active", true);
        }
}

function prewikka_loadTab(settings)
{
        $("#top_view_navbar .dropdown").removeClass("open");

        var type = settings['type'] || "";

        if ( settings['dataType'] == undefined )
                settings['dataType'] = "json";

        if ( settings['history'] == undefined )
                settings['history'] = true;

        settings['beforeSend'] = function(xhr) {
                _url2menu(settings['url'].split("?")[0]);

                if ( window._prewikka_current_xhr != null)
                        window._prewikka_current_xhr.abort();

                window._prewikka_current_xhr = xhr;
        };


        settings['complete'] = $.makeArray(settings['complete']);
        settings['complete'].push(function(xhr) {
                window._prewikka_current_xhr = null;
        });

        return $.ajax(settings).success(function(data) {
                if ( settings['history'] && type.toUpperCase() != "POST" ) {
                        var url = settings['url'];

                        if ( settings['data'] )
                                url += "?" + settings['data'];

                        history.pushState(url, '', url);

                        if ( settings['success'] )
                                settings['success']();
                }
                prewikka_drawTab(data);
                window.scrollTo(0, 0);
        });
}


function prewikka_widget(settings)
{
        var type = settings['type'] || "";

        if ( settings['dataType'] == undefined )
                settings['dataType'] = "json";

        var dlg = $('<div class="widget-dialog" />');

        var conf = _mergedict({ width: $("#_main").width() * 0.9,
                                height: "auto",
                                autoOpen: false,
                                maxWidth: $("#_main").width(),
                                maxHeight: prewikka_dialog_getMaxHeight(),
                                draggable: true,
                                modal: true,
                                buttons: undefined,
                                position: { my: "center", at: "center", "of": window },
                                collision: "fit",
                                appendTo: "#_main",
                                close: function() {
                                        $(this).dialog('destroy').remove();
                                }
        }, settings['dialog']);

        return $.ajax(settings).done(function(data) {
                var content = $(data.content);

                if ( ! conf["buttons"] ) {
                        var btbl = Array();

                        $(content).find(":input.widget-control").each(function(idx, data) {
                                $(this.form).uniqueId();
                                var btn = { 'class': $(this).attr("class"),
                                            html: $(this).html() ? $(this).html() : $(this).val(),
                                            type: $(this).attr("type"),
                                            form: $(this.form).attr("id"),
                                            click: $.noop
                                };
                                btbl.push(btn);
                        }).remove();

                        if ( btbl.length == 0 )
                                btbl.push({ text: "Close", 'class': "btn btn-default", click: function() { $(this).dialog('destroy').remove() } });

                        conf["buttons"] = btbl;
                }

                /*
                 * Create the dialog before appending the content, so that the content might depend on the dialog
                 * Open the dialog before loading the content, as some libraries need elements to be displayed
                 * Force a dialog re-positioning due to the content change
                 */
                $(dlg).dialog(conf);
                $(dlg).dialog("open");
                $(dlg).append(content);
                $(dlg).dialog("option", "position", conf.position);
        });
}


function prewikka_EventSource(config)
{
    var jsonStream = new EventSource(config['url']);

    if ( config['error'] == undefined ) {
        config['error'] = function(e) {
            prewikka_dialog(e);
            jsonStream.close();
        };
    }

    if ( config['close'] == undefined ) {
        config['close'] = function(e) {
            jsonStream.close();
        };
    }

    jsonStream.addEventListener('close', function(e) {
        config["close"](e)
        jsonStream.close();
    });

    var decode_json = function(e) { return $.parseJSON(e.data) };
    if ( config['type'] != undefined && config['type'] != 'json' ) {
        decode_json = function(e) { return e };
    }

    for ( ev in config['events'] ) {
        (function(_ev) {
            jsonStream.addEventListener(_ev, function(e) { config['events'][_ev](decode_json(e)) });
        })(ev);
    }

    jsonStream.onmessage = function(e) { config['message'](decode_json(e)) };
    jsonStream.onerror = function(e) { config['error'](decode_json(e)) };

    return jsonStream;
}
