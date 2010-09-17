    
var refreshId = null;
var logFileRefreshId = null;
var currentSerialNumber = null;

var showingTestPanel = false;
var smShowingOverviewTab = false;

var sparklineDataMap = {};
var sparklineMaxPoints = 22;
var sparklineAnalogInOptions = {height: "15px", minSpotColor: false, maxSpotColor: false, spotColor: "#A20000", lineColor: "#004276", fillColor: "#E6F3FF" };
var sparklineDigitalInOptions = {type:'bar', height: "16px", barColor: "#004276" };
var sparklineDigitalOutOptions = {type:'bar', height: "16px", barColor: "#A20000" };

var sparklineLQIOptions = $.extend({}, sparklineAnalogInOptions);
sparklineLQIOptions.normalRangeMin = 100;
sparklineLQIOptions.normalRangeMax = 255;
sparklineLQIOptions.normalRangeColor = "#DEDEDE";
sparklineLQIOptions.fillColor = false;
sparklineLQIOptions.chartRangeMin = 0;
sparklineLQIOptions.chartRangeMax = 255;

var sparklineVbattOptions = $.extend({}, sparklineAnalogInOptions);
sparklineVbattOptions.normalRangeMin = 3;
sparklineVbattOptions.normalRangeMax = 4.75;
sparklineVbattOptions.fillColor = false;
sparklineVbattOptions.chartRangeMin = 1.5;
sparklineVbattOptions.chartRangeMax = 5;

var CloudDotLastUsername = "";
var CloudDotLastApikey = "";


$(document).ready(function() {
    $("#tabs").tabs();
    $("#sm-tabs").tabs();
    setupHashChange();    
    setupTestPanelConnectionLinks();
    setupRenameLinks();
    setupEditLinks();
    setupStopLoggingLinks();
    setupDialog();
    setupLogCheckboxes();
    setupLogFileScanning();
    setupTabSelect();
    setupSaveLoadDeleteConfigLinks();
    setupTimerCounterLink();
    setupCloudDotLinks();
    setupConfigureMoteLinks();
    getDeviceList();
    updateLogBar();
    setupExitButton();
});

function setupHashChange() {
  // Override the default behavior of all `a` elements so that, when
  // clicked, their `href` value is pushed onto the history hash
  // instead of being navigated to directly.
  
  // Bind a callback that executes when document.location.hash changes.
  $(window).bind("hashchange", urlHashChange);

  // Since the event is only triggered when the hash changes, we need
  // to trigger the event now, to handle the hash the page may have
  // loaded with.
  $(window).trigger( "hashchange" );
}

function urlHashChange(e) {
    stopScanning();
    sparklineDataMap = {};
    showingTestPanel = false;
    smShowingOverviewTab = false;
    $("#test-panel-table").empty();
    var serialNumber = e.getState( "d" );

    if (!serialNumber) {
        var bridgeSerialNumber = e.getState( "sm" );
    }

    if (serialNumber) {
        highlightCurrentSerialNumber(serialNumber);
        handleSelectDevice(serialNumber);
    } else if (bridgeSerialNumber) {
        highlightCurrentSerialNumber(bridgeSerialNumber);
        smHandleSelectBridge(bridgeSerialNumber);
    } else {
        $("#tabs").hide();
        $("#sm-tabs").hide();
        $("#device-summary-list").show();
    }
}

function highlightCurrentSerialNumber(serialNumber) {
    $("#device-name-list li").removeClass("ui-helper-reset ui-widget-header pop");
    $("#device-name-list li a").removeClass("current-name");
    $("#"+serialNumber).addClass("ui-helper-reset ui-widget-header pop");
    $("#"+serialNumber+" a").addClass("current-name");
    if ($("#"+serialNumber+" a").text()) {
      document.title = $("#"+serialNumber+" a").text() + " | LabJack CloudDot Grounded";
    }
}

function stopScanning() {
    if (refreshId != null) {
        clearTimeout(refreshId);
    }
}

function restartScanning() {
    if (refreshId != null) {
        clearTimeout(refreshId);
    }
    refreshId = setTimeout(callScan, 500);
}

function showTopMessage(message) {
    $("#latest-message-bar").html(message).show().delay(10000).hide("fast");
}

function setupDialog() {
    $("#dialog").dialog({
        modal: true,
        autoOpen: false
    });
}

function dialogDone() {
    $("#dialog").dialog("close");
    callScan();
    restartScanning();
}

function setupLogCheckboxes() {
    $(".log-checkbox").live('click', findCheckedCheckboxesAndLog);
}

function findCheckedCheckboxesAndLog() {

    var logList = highlightCheckedCheckboxes();
    logList = logList.join(",");
    $.get("/logs/start", {serial : currentSerialNumber, headers : logList}, updateLogBar, "json");
}

function highlightCheckedCheckboxes() {
    var logList = [];
    $(".log-checkbox:not(:checked)").each(function() {
        $(this).closest("tr").removeClass("ui-state-highlight");
    });
    $(".log-checkbox:checked").each(function() {
        var textVal = $(this).closest("tr").addClass("ui-state-highlight").find(".loggable-connection-link").text();
        logList.push(textVal);
    });
    return logList;
}

function updateLogBar() {
    $.get("/logs/loggingSummary", {}, function(data) { $("#log-bar").html(data); }, "string");
}

function setupLogFileScanning() {
    if ($("body").hasClass("logs")) {
        if (logFileRefreshId != null) {
            clearTimeout(logFileRefreshId);
        }
        logFileRefreshId = setInterval(callLogFileScan, 1000);
    }
}

function callLogFileScan() {
    $("#log-wrapper").load("/logs/logFileList");
}

function setupTabSelect() {
    var $tabs = $("#tabs").tabs();
    $tabs.bind("tabsselect", function(event, ui) {
        updateTabContent(ui.index);    
    });
}

function updateTabContent(tabIndex) {
    if (currentSerialNumber == null) {
        return;
    }
    if (tabIndex == undefined) {
        var $tabs = $("#tabs").tabs();
        tabIndex = $tabs.tabs('option', 'selected');
    }
    if (tabIndex == 3) {
        $.get("/devices/support/" + currentSerialNumber, {}, function(data)  {$("#support-tab").html(data); });
    }
    else if(tabIndex == 2) {
    
        $.get("/clouddot/info/"+currentSerialNumber, function(returnJson) {
            $("#clouddot-tab").html(returnJson.html);
            // Disable the CloudDot username submit button
            $("#user-form-submit").attr("disabled", "disabled");

            if (returnJson.connected) {
                showCloudDotConnected(false);
            } else {
                showCloudDotDisconnected(false);
            }
            $("a.button").button();
        }, "json");
    }
    else if(tabIndex == 1) {
        $.get("/config/filelist/" + currentSerialNumber, {}, function(data) {
            $("#config-file-list").html(data); 
            $("a.button").button();
        });
    }
}

function setupSmTabSelect() {
    var $tabs = $("#sm-tabs").tabs();
    $tabs.bind("tabsselect", function(event, ui) {
        updateSmTabContent(ui.index);
    });
}

function updateSmTabContent(tabIndex) {
    console.log("updateSmTabContent");
}

function setupSaveLoadDeleteConfigLinks() {
    $("#save-config-link").live("click", function() {
        var targetUrl = $(this).attr("href");
        $.get(targetUrl, function(data) {
            $("#tabs").tabs("select", 1);
            showTopMessage(data);
        });
        return false;
    });
    $("a.load-config-link").live("click", function() {
        var targetUrl = $(this).attr("href");
        $.get(targetUrl, function(data) {
            $("#tabs").tabs("select", 0);
            showTopMessage(data);
            $(window).trigger( "hashchange" );
        });
        return false;
    });
    $("a.delete-config-link").live("click", function() {
        var targetUrl = $(this).attr("href");
        var configRow = $(this).closest("li");
        $.get(targetUrl, function(data) {
            showTopMessage(data);
            $(configRow).fadeOut(500);
        });
        return false;
    });
}

// Return the input value, with 0 if undefined
function  getFormInputValue(selectorString) {
    var selectedValue = $(selectorString).val();
    if (selectedValue == undefined || selectedValue == "") {
        selectedValue = 0;
    }
    return selectedValue;
}


function getUpdateTimerCounterOptions(serial) {
    var updateTimerCounterOptions = {};
    updateTimerCounterOptions.serial = serial;
    updateTimerCounterOptions.timerClockBase    = getFormInputValue("select[name='timerClockBase']");
    updateTimerCounterOptions.timerClockDivisor = getFormInputValue("input[name='timerClockDivisor']");
    updateTimerCounterOptions.pinOffset         = getFormInputValue("select[name='pinOffset']");

    updateTimerCounterOptions.counter0Enable    = getFormInputValue("input[name='counter0Enable']:checked");
    updateTimerCounterOptions.counter1Enable    = getFormInputValue("input[name='counter1Enable']:checked");
    
    var timerKey;
    for (var i = 0; i < $(".timer-wrapper").length; i++) {
        timerKey = "timer" + i + "Enabled";
        updateTimerCounterOptions[timerKey]     = getFormInputValue("input[name="+timerKey+"]:checked");
        timerKey = "timer" + i + "Mode";
        updateTimerCounterOptions[timerKey]        = getFormInputValue("select[name="+timerKey+"]");
        timerKey = "timer" + i + "Value";
        updateTimerCounterOptions[timerKey]       = getFormInputValue("input[name="+timerKey+"]");
    }

    return updateTimerCounterOptions;
}

function updateTCPinLocationSummary() {
    var updateTimerCounterOptions = getUpdateTimerCounterOptions(currentSerialNumber);
    $("#tc-connection-dialog-pin-location-summary").load("/devices/tcPinLocationSummary/", updateTimerCounterOptions);
}

function findAndUpdateTimerValueInput() {
    var nearestValueInput = $(this).closest(".timer-wrapper").find(".timer-value");
    var timerWrapper = $(this).closest(".timer-wrapper");
    updateTimerValueInput(nearestValueInput, $(this).val());
    setTimerHelpUrl(timerWrapper);

    // Special consideration for Quadrature Input, mode 8
    // Get the pair of this timer 0 <-> 1, 2 <-> 3, and so on
    var thisTimerNumber = parseInt($(this).closest(".timer-wrapper").find(".timer-enable-box").attr("timer-number"));
    if (thisTimerNumber % 2 == 1) {
        var timerPair = thisTimerNumber - 1;
    } else {
        var timerPair = thisTimerNumber + 1;
    }
    var $timerPairBox = $("input[timer-number="+timerPair+"]");
    var $timerPairSelect = $timerPairBox.closest(".timer-wrapper").find(".timer-config-inputs select");
    var $timerPairValueInput = $timerPairBox.closest(".timer-wrapper").find(".timer-value");
    var timerPairWrapper = $timerPairBox.closest(".timer-wrapper");
    if ($(this).val() == 8) {
        // If we select Quadrature Input set the timer pair to Quadrature Input, too
        enableTimerInputSelection($timerPairBox);
        $timerPairBox.attr("checked", "checked");
        $timerPairBox.trigger("change");
        $timerPairSelect.val(8);
        updateTimerValueInput($timerPairValueInput, 8);
        setTimerHelpUrl(timerPairWrapper);
    }
    else {
        // If we don't select Quadrature Input, make sure the pair isn't Quadrature Input either
        if ($timerPairSelect.val() == 8) {
            $timerPairSelect.val(10); // Set it to System timer low read
        updateTimerValueInput($timerPairValueInput, 10);
        setTimerHelpUrl(timerPairWrapper);
        }
    }
}

function updateTimerValueInput(timerInputElement, selectedIndex) {
    var inputsThatRequireValue = [1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0];
    var defaultValues = [32768, 32768, "", "", "", "", 1, 1, "", 5, "", "", "", ""];

    if (!$(timerInputElement).val()) {
        $(timerInputElement).val(defaultValues[selectedIndex]);
    }

    if (inputsThatRequireValue[selectedIndex]) {
        $(timerInputElement).removeAttr("disabled").closest("label").show();
    } else {
        $(timerInputElement).attr("disabled", "disabled").removeAttr("value").closest("label").hide("fast");
    }
}


function disableClockDivisorOrCounter0IfNeeded() {
    if ($("select[name='timerClockBase']").val() > 2) {
        $("input[name='counter0Enable']").attr("disabled", "disabled").removeAttr("checked").next(".enable-counter-text").addClass("counter0-taken").text("Counter0 taken by timer clock divisor");
        $("input[name='timerClockDivisor']").removeAttr("disabled").closest("label").show();
        if($("input[name='timerClockDivisor']").val() == "") {
            $("input[name='timerClockDivisor']").val(1);
        }
    }
    else {
        $("input[name='counter0Enable']").removeAttr("disabled").next(".enable-counter-text").removeClass("counter0-taken").text("Enable Counter0");
        $("input[name='timerClockDivisor']").attr("disabled", "disabled").val("").closest("label").hide("fast");
    }
}

function disableTimerInputChildren(timerWrapper) {
    $(timerWrapper).find(".timer-config-inputs select, .timer-config-inputs input").attr("disabled","disabled").closest("label").hide("fast");
    $(timerWrapper).find(".more-info").hide();
}

function enableTimerInputChildren(timerWrapper) {
    $(timerWrapper).find(".timer-config-inputs select, .more-info").removeAttr("disabled").closest("label").show();
    updateTimerValueInput($(timerWrapper).find(".timer-value"), $(timerWrapper).find(".timer-config-inputs select").val());
    setTimerHelpUrl(timerWrapper);
    $(timerWrapper).find(".more-info").show();
}

function setTimerHelpUrl(timerWrapper) {
    var $timerSelect = $(timerWrapper).find(".timer-config-inputs select");
    var timerSelectVal = $timerSelect.val();
    var timerHelpUrl = $timerSelect.find("option[value=" + timerSelectVal + "]").attr("helpurl");
    var timerHelpText = $timerSelect.find("option[value=" + timerSelectVal + "]").text();
    $(timerWrapper).find(".timer-config-help-link").attr("href", timerHelpUrl).text(timerHelpText);
}

function disableTimerInputSelection(timerInput) {
    disableTimerInputChildren($(timerInput).closest(".timer-wrapper"));
    $(timerInput).attr("disabled","disabled").removeAttr("checked").closest("label").addClass("weak");
}

function enableTimerInputSelection(timerInput) {
    $(timerInput).removeAttr("disabled").closest("label").removeClass("weak");
}


function timerCounterEnabledRules() {
    var firstUnchecked = null;

    // Hide the extra inputs for unchecked timers
    // Also, remember the firstUnchecked timer for the next loop
    $(".timer-enable-box").each(function() {
        if($(this).is(':checked')) {
            enableTimerInputChildren($(this).closest(".timer-wrapper"));
        } else {
            disableTimerInputChildren($(this).closest(".timer-wrapper"));
            if (firstUnchecked == null) {
                firstUnchecked = $(this).attr("timer-number");
            }
        }
    });
    if (firstUnchecked != null) {
        $(".timer-enable-box").each(function() {
            if ($(this).attr("timer-number") > firstUnchecked) {
                disableTimerInputSelection($(this));
            }
            else if ($(this).attr("timer-number") == firstUnchecked) {
                enableTimerInputSelection($(this));
            }
        });
    }
}

function setupTimerCounterLink() {

    $("select[name='pinOffset']").live("change", updateTCPinLocationSummary);

    $("select.timer-mode-select").live("change", findAndUpdateTimerValueInput);

    $(".timer-enable-box").live("change", timerCounterEnabledRules);

    // A timerClockBase with a divisor (>2 in the list) requires Counter0
    $("select[name='timerClockBase']").live("change", disableClockDivisorOrCounter0IfNeeded);

    $(".timer-counter-config-link").live("click", function() {
        stopScanning();
        var targetUrl = $(this).attr("href");
        $.get(targetUrl, function(returnJson) {
            $("#dialog").html(returnJson.html);
            $("#tc-connection-dialog-tabs").tabs();
            $("#tc-connection-dialog-tabs").bind("tabsselect", function(event, ui) {
                if (ui.index == 2) {
                    updateTCPinLocationSummary();    
                }
            });
            if (returnJson.counterSelected == "true") {
                $("#tc-connection-dialog-tabs").tabs("select", 1);
            }
            $("#tc-connection-dialog-pin-location-summary").html(returnJson.tcPinLocationHtml);
            $("#dialog").dialog('option', 'title', "Timers & Counters");
            $("#dialog").dialog('option', 'width', 525);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    var updateTimerCounterOptions = getUpdateTimerCounterOptions(returnJson.serial);
                    $.get("/devices/updateTimerCounterConfig", updateTimerCounterOptions, function() { dialogDone(); $(window).trigger( "hashchange" ); });
                },
                "Cancel": dialogDone
            });
            $("#dialog").dialog('open');
            timerCounterEnabledRules();
            disableClockDivisorOrCounter0IfNeeded();
            $("select.timer-mode-select").each(findAndUpdateTimerValueInput);
        }, "json");
        return false;
    });
}

function clearSparklineIfNeeded(oldState, newState, fioNumber) {
    if (oldState != newState) {
        sparklineDataMap[fioNumber] = [];
    }
}

function callU6UpdateInputInfo(inputConnection, chType, negChannel, state, gainIndex, resolutionIndex) {
    var updateInputInfoOptions = {serial : currentSerialNumber, inputNumber : inputConnection, chType : chType};
    if (negChannel != undefined) {
        updateInputInfoOptions.negChannel = negChannel;
    }
    if (state != undefined) {
        updateInputInfoOptions.state = state;
    }
    if (gainIndex != undefined) {
        updateInputInfoOptions.gainIndex = gainIndex;
    }
    if (resolutionIndex != undefined) {
        updateInputInfoOptions.resolutionIndex = resolutionIndex;
    }
    $.get("/devices/updateInputInfo", updateInputInfoOptions, dialogDone);
}

function callU3UpdateInputInfo(inputConnection, chType, negChannel, state) {
    var updateInputInfoOptions = {serial : currentSerialNumber, inputNumber : inputConnection, chType : chType};
    if (negChannel != undefined) {
        updateInputInfoOptions.negChannel = negChannel;
    }
    if (state != undefined) {
        updateInputInfoOptions.state = state;
    }
    //console.log("callU3UpdateInputInfo");
    //console.log(updateInputInfoOptions);
    $.get("/devices/updateInputInfo", updateInputInfoOptions, dialogDone);
}

function getInputInfo(inputConnection) {
    stopScanning();
    //console.log(currentSerialNumber);
    //console.log(inputConnection);
    $.get("/devices/inputInfo", {serial : currentSerialNumber, inputNumber : inputConnection}, handleInputInfo, "json");

}

function handleInputInfo(inputInfoJson) {
    //console.log(inputInfoJson);
    $("#dialog").empty();

    // Check for DAC0 or DAC1    
    if (inputInfoJson.connectionNumber == 5000 || inputInfoJson.connectionNumber == 5002) {
        $("#dialog").html(inputInfoJson.html);
        $("#dac-slider").slider({
                 range: "min",
                    value:inputInfoJson.state,
                    min: 0,
                    max: 5,
                    step: 0.01,
                    slide: function(event, ui) {
                        $("#dac-value").val(ui.value);
                    }
                });
        $("#dac-value").val($("#dac-slider").slider("value")).blur(function() {
            var newValue = $(this).val();
            if (newValue >=0 && newValue <= 5.0) {
                $("#dac-slider").slider("option", "value", $(this).val());
            }
        });
        $("#dac-form").submit(function() {
            var newValue = $("#dac-value").val();
            //console.log(newValue);
            if (newValue >=0 && newValue <= 5.0) {
                $.get("/devices/" + currentSerialNumber + "/writeregister", {addr : inputInfoJson.connectionNumber, value : newValue}, function (data) {return true;}, "json");
            }
            dialogDone();
            return false;
        });

        $("#dialog").dialog('option', 'title', inputInfoJson.label);
        $("#dialog").dialog('option', 'width', 425);
        $("#dialog").dialog('option', 'buttons', { 
            "Save": function() {
                $("#dac-form").submit();
            },
            "Cancel": dialogDone
        });
        $("#dialog").dialog('open');
        return;
    }

    // Device-specific connnections    
    if (inputInfoJson.device.devType == 3) {
        $("#dialog").html(inputInfoJson.html);

        $("#u3-connection-dialog-tabs").tabs();
        var removeSelector = "select[name='neg-channel'] option[value=" + inputInfoJson.fioNumber + "]";
        $(removeSelector).remove();
        if (inputInfoJson.chType != "analogIn") {
            $("#u3-connection-dialog-tabs").tabs('select', '#u3-connection-dialog-tabs-digital');
            if (inputInfoJson.chType == "digitalIn") {
                $("input[name='digital']:nth(0)").attr("checked","checked");        
            } else {
                if (inputInfoJson.state == 0) {
                    $("input[name='digital']:nth(1)").attr("checked","checked");
                } else {
                    $("input[name='digital']:nth(2)").attr("checked","checked");
                }
            }
        } else {
            if (inputInfoJson.negChannel == 31) {
                $("input[name='analog']:nth(0)").attr("checked","checked");
            } else if (inputInfoJson.negChannel == 32) {
                $("input[name='analog']:nth(1)").attr("checked","checked");
            } else if (inputInfoJson.negChannel >= 0 && inputInfoJson.negChannel < 31) {
                $("input[name='analog']:nth(2)").attr("checked","checked");
                $("select[name='neg-channel']").val(inputInfoJson.negChannel)
            }
        }
       
        $("#dialog").dialog('option', 'title', inputInfoJson.label);
        $("#dialog").dialog('option', 'width', 425);
        $("#dialog").dialog('option', 'buttons', { 
            "Save": function() {
                var tabIndex = $("#u3-connection-dialog-tabs").tabs('option', 'selected');
                var analogSelected = (tabIndex == 0) ? true : false;
                if (analogSelected) {
                    var newChType = "analogIn";
                    var negChannel = 31;
                    //console.log("analog selected");
                    var analogSelection = $("input[name='analog']:checked").val();
                    //console.log(analogSelection);
                    if (analogSelection == "single-special") {
                        negChannel = 32;
                    } else if (analogSelection == "differential") {
                        negChannel = $("select[name='neg-channel']").val();
                    }
                    callU3UpdateInputInfo(inputInfoJson.fioNumber, newChType, negChannel, null);
                } else {
                    //console.log("digital selected");
                    var digitalSelection = $("input[name='digital']:checked").val();
                    //console.log(digitalSelection);

                    var newChType = '';
                    var newState = null;
                    if (digitalSelection == "digital-input") {
                        newChType = "digitalIn";
                    } else if (digitalSelection == "digital-output-low") {
                        newChType = "digitalOut";
                        newState = 0;
                    } else if (digitalSelection == "digital-output-high") {
                        newChType = "digitalOut";
                        newState = 1;
                    }


                    clearSparklineIfNeeded(inputInfoJson.chType, newChType, inputInfoJson.fioNumber);

                    callU3UpdateInputInfo(inputInfoJson.fioNumber, newChType, null, newState);
                }
            },
            "Cancel": dialogDone
        });
        $("#dialog").dialog('open');
        //console.log("U3");    
    }
    else if (inputInfoJson.device.devType == 6 || inputInfoJson.device.devType == 9) {
        $("#dialog").html(inputInfoJson.html);
        if (inputInfoJson.chType == "analogIn") {
            $("select[name='gain']").val(inputInfoJson.gainIndex);
            $("select[name='resolution']").val(inputInfoJson.resolutionIndex);
            if (inputInfoJson.negChannel != 31) {
                $("input[name='differential']").attr("checked", "checked");
            }
        } else {
            if (inputInfoJson.chType == "digitalIn") {
                $("input[name='digital']:nth(0)").attr("checked","checked");        
            } else {
                if (inputInfoJson.state == 0) {
                    $("input[name='digital']:nth(1)").attr("checked","checked");
                } else {
                    $("input[name='digital']:nth(2)").attr("checked","checked");
                }
            }
        }
        $("#connection-dialog-tabs").tabs();
        $("#dialog").dialog('option', 'title', inputInfoJson.label);
        $("#dialog").dialog('option', 'width', 425);
        $("#dialog").dialog('option', 'buttons', { 
            "Save": function () {
                
                var newNegChannel = $("input[name='differential']:checked").val();
                if (newNegChannel) {
                    newNegChannel = 1;
                }
                var newGainIndex = $("select[name='gain']").val();
                var newResolutionIndex = $("select[name='resolution']").val();

                var newChType = '';
                var newState = null;
                if (inputInfoJson.chType == "analogIn") {
                    newChType = inputInfoJson.chType;
                }
                else {
                    var digitalSelection = $("input[name='digital']:checked").val();
                    if (digitalSelection == "digital-input") {
                        newChType = "digitalIn";
                    } else if (digitalSelection == "digital-output-low") {
                        newChType = "digitalOut";
                        newState = 0;
                    } else if (digitalSelection == "digital-output-high") {
                        newChType = "digitalOut";
                        newState = 1;
                    }
                }
                callU6UpdateInputInfo(inputInfoJson.fioNumber, newChType, newNegChannel, newState, newGainIndex, newResolutionIndex);
            },
            "Cancel": dialogDone
        });
        $("#dialog").dialog('open');
    }
    else {
        //console.log("Not a U3 or U6");
    }
}


function setupTestPanelConnectionLinks() {
    $(".test-panel-connection-link").live("click", function(e) {
        var inputConnection = $(this).attr("inputConnection");
        getInputInfo(inputConnection);
        return false;
    });
    $(".digital-out-toggle-link").live("click", function(e) {
        stopScanning();
        $(this).addClass("toggling");
        var toggleLink = $(this);
        var inputConnection = $(this).attr("inputConnection");
        $.get("/devices/toggleDigitalOutput", {serial : currentSerialNumber, inputNumber : inputConnection}, function (data) {handleScan(data); toggleLink.removeClass("toggling");}, "json");
        return false;
    });
    $(".reset-counter-link").live("click", function(e) {
        stopScanning();
        $(this).addClass("toggling");
        var toggleLink = $(this);
        var inputConnection = $(this).attr("inputConnection");
        $.get("/devices/resetCounter", {serial : currentSerialNumber, inputNumber : inputConnection}, function (data) {handleScan(data); toggleLink.removeClass("toggling");}, "json");
        return false;
    });
}

function setupRenameLinks() {
    $(".rename-link").live("click", function(e) {
        $.get("/devices/" + currentSerialNumber + "/getName", {}, function(data) { 
            $("#dialog").empty();
            $("#dialog").html('<form id="rename-form"><p><input type="text" id="rename-value" size="30" /></p></form>');
            $("#rename-form").submit(function() {
                var newName = $("#rename-value").val();
                $.get("/devices/" + currentSerialNumber + "/setName", {name : newName}, function(data) { $(".current-name").text(newName); document.title = newName + " | LabJack CloudDot Grounded"; });
                dialogDone();
                return false;
            });
            $("#dialog").dialog('option', 'title', "Rename " + data.result);
            $("#dialog").dialog('option', 'width', 425);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    $("#rename-form").submit();
                },
                "Cancel": dialogDone
            });
            $("#rename-value").val(data.result);
            $("#dialog").dialog('open');
        
        });
    
        return false;
    });
}

function setupEditLinks() {
    // For editing Local ID
    $(".edit-localid-link").live("click", function(e) {
        var devtype = $(".edit-localid-link").attr("devtype");
        $.get("/forms/editLocalIdForm", {}, function(data) { 
            $("#dialog").empty();
            $("#dialog").html(data);
            $("#edit-form").submit(function() {
                var newId = $("#edit-value").val();
                var urlString = "/devices/" + currentSerialNumber;
                
                if(devtype == "3") {
                     urlString = urlString + "/configu3";
                }
                else if(devtype == "6") {
                    urlString = urlString + "/configu6";
                }
                else if(devtype == "9") {
                    urlString = urlString + "/commconfig";
                }
                
                $.get(urlString, {LocalID : newId}, function(data) { $("#localId-value").html(newId); });
                dialogDone();
                return false;
            });
            $("#dialog").dialog('option', 'title', "Change Local ID");
            $("#dialog").dialog('option', 'width', 425);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    $("#edit-form").submit();
                },
                "Cancel": dialogDone
            });
            $("#edit-value").val($("#localId-value").html());
            $("#dialog").dialog('open');
        });
    
        return false;
    });
    
    // UE9 Only: Editing Comm. Config
    $(".edit-commconfig-link").live("click", function(e) {
        $.get("/forms/editCommConfigForm", {}, function(data) { 
            $("#dialog").empty();
            $("#dialog").html(data);
            $("#edit-form").submit(function() {
                // Call CommConfig low-level function
                var urlString = "/devices/" + currentSerialNumber+"/commConfig";
                
                // Read in all the form values:
                var enableDhcp = $("#enable-dhcp-value:checked").val();
                if(enableDhcp == undefined || enableDhcp == '') {
                    enableDhcp = 0;
                }
                
                var ipAddress = $("#ip-address-value").val();
                var subnet = $("#subnet-mask-value").val();
                var gateway = $("#gateway-value").val();
                var portA = $("#porta-value").val();
                var portB = $("#portb-value").val();
                
                                
                $.get(urlString, {IPAddress : ipAddress, Gateway : gateway, Subnet : subnet, PortA : portA, PortB : portB, DHCPEnabled : enableDhcp}, function(data) {
                    if(data.result.DHCPEnabled == true) {
                        $("#enable-dhcp").html("Enabled");
                    } else {
                        $("#enable-dhcp").html("Disabled");
                    }
                    
                    $("#ip-address").html($("#ip-address-value").val());
                    $("#subnet-mask").html($("#subnet-mask-value").val());
                    $("#gateway").html($("#gateway-value").val());
                    $("#porta").html($("#porta-value").val());
                    $("#portb").html($("#portb-value").val());
                    
                });
                dialogDone();
                return false;
            });
            $("#dialog").dialog('option', 'title', "Change Communication Settings");
            $("#dialog").dialog('option', 'width', 425);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    $("#edit-form").submit();
                },
                "Cancel": dialogDone
            });
            
            var dhcpEnabled = false;
            if($("#enable-dhcp").html() == "Enabled") {
                $("#enable-dhcp-value").attr("checked", "yes");
                dhcpEnabled = true;
            }
            
            $("#ip-address-value").val($("#ip-address").html());
            $("#subnet-mask-value").val($("#subnet-mask").html());
            $("#gateway-value").val($("#gateway").html());
            
            if(dhcpEnabled == true) {
                $("#ip-address-value").attr("disabled", "disabled");
                $("#subnet-mask-value").attr("disabled", "disabled");
                $("#gateway-value").attr("disabled", "disabled");
            }
            
            $("#enable-dhcp-value").live('click', function() {
                var enableDhcp = $("#enable-dhcp-value:checked").val();
                if(enableDhcp == undefined || enableDhcp == '') {
                    $("#ip-address-value").removeAttr("disabled");
                    $("#subnet-mask-value").removeAttr("disabled");
                    $("#gateway-value").removeAttr("disabled");
                } else {
                    $("#ip-address-value").attr("disabled", "disabled");
                    $("#subnet-mask-value").attr("disabled", "disabled");
                    $("#gateway-value").attr("disabled", "disabled");
                }
            });
            
            $("#porta-value").val($("#porta").html());
            $("#portb-value").val($("#portb").html());
            
            $("#dialog").dialog('open');
        });
    
        return false;
    });
}

function setupStopLoggingLinks() {
    $(".stop-link").live("click", function(e) {
        var stopUrl = $(this).attr("stopurl");
        $.get(stopUrl, {}, function(data) { $("#log-bar").html(data); $(window).trigger( "hashchange" ); }, "string");
        return false;
    });
}

function sparklineMinMax(sparklineType, deviceType) {
    minMax = {};
    switch (sparklineType) {
        case "analogIn":
            if (deviceType == 6) {
                minMax.min = -10;
                minMax.max = 10;
            } else {
                minMax.min = 0;
                minMax.max = 3.3;
            }
            break;
        case "digitalIn":
        case "digitalOut":
            minMax.min = 0;
            minMax.max = 1;
            break;
        case "internalTemp":
            minMax.min = 60;
            minMax.max = 90;
            break;
        default:
            minMax.min = 0;
            minMax.max = 5;
            break;
    }
    return minMax;
}


function callScan() {
    $(".scanning-indicator").addClass("ui-icon ui-icon-bullet");
    $.ajax({
        url: "/devices/scan", 
        data: {serial : currentSerialNumber}, 
        success: handleScan, 
        dataType: "json"
    });
}

function handleScan(data) {
    if (data.length == 0) {
        $("#test-panel-tab, #scan-bar").html("Lost connection. Check the LabJack and <a href='/'>reload</a>.");
        showingTestPanel == false;
        return;
    }

    $(".scanning-indicator").removeClass("ui-icon ui-icon-bullet");

    if (showingTestPanel == false) {
        
        $("#test-panel-table").jqGrid({
          datatype: "local",
          height: "100%",
          colNames:['Connection','State','Log'],
          colModel:[
               {name:'connection',index:'connection', width:250,  sortable:false},
               {name:'state',index:'state', width:350, sortable:false},
               {name:'log',index:'log', width:100, sortable:false}
          ],
          multiselect: false,
          caption: "Test Panel",
          beforeSelectRow : function() { return false; }
        });


        var count = 0;
        for (var d in data) {

            var connectionText = data[d].connection;
            var connectionNumber = data[d].connectionNumber;
            var thisState = data[d].state;
            var thisValue = data[d].value;
            var thisChType = data[d].chType;
            var thisLogging = data[d].logging;
            sparklineDataMap[count] = [];
            sparklineDataMap[count].push(thisValue);

            if (sparklineDataMap[count].length > sparklineMaxPoints) {
                sparklineDataMap[count].splice(0,1);
            }
            
            
            var obj = { connection : "<a href='#' class='test-panel-connection-link loggable-connection-link' inputConnection='"+connectionNumber+"' title='Configure " + connectionText + "'>"+connectionText+"</a>", state: "<span class='test-panel-sparkline " + thisChType + "'></span>" + "<span class='test-panel-state'>"+thisState + "</span>", log: "<input type='checkbox' class='log-checkbox' />"};
            if (thisLogging) {
                obj.log = "<input type='checkbox' class='log-checkbox' checked='yes' />";
            }
            if (connectionText == "Internal Temperature") {
                obj.connection = "<span class='loggable-connection-link'>" + connectionText + "</span>"; // No link
            }
            // Special link and class for timers and counters
            if (thisChType == "timer") {
                obj.connection = "<a href='/devices/timerCounterConfig/" + currentSerialNumber + "' class='timer-counter-config-link loggable-connection-link' inputConnection='"+connectionNumber+"' title='Configure " + connectionText + "'>"+connectionText+"</a>";            
            }
            else if (thisChType == "counter" || thisChType == "counter-divisor") {
                obj.connection = "<a href='/devices/timerCounterConfig/" + currentSerialNumber + "?counterSelected=true' class='timer-counter-config-link loggable-connection-link' inputConnection='"+connectionNumber+"' title='Configure " + connectionText + "'>"+connectionText+"</a>";            
            }

            $("#test-panel-table").jqGrid('addRowData', count, obj);
            highlightCheckedCheckboxes();
            count++;
        }
        
        $("#save-config-link").button();
        $(".hide-at-start").show();
        showingTestPanel = true;
    } else {
        var count = 0;
        for (var d in data) {          
            var selectorCount = "#" + count;
            var connectionText = data[d].connection;
            var connectionNumber = data[d].connectionNumber;
            var thisState = data[d].state;
            var thisValue = data[d].value;
            var thisChType = data[d].chType;
            sparklineDataMap[count].push(thisValue);
            
            if (sparklineDataMap[count].length > sparklineMaxPoints) {
                sparklineDataMap[count].splice(0,1);
            }
            
            
            if (thisChType == "digitalOut") {
                thisState = thisState + "<a href='#' class='digital-out-toggle-link' inputConnection='"+connectionNumber+"' title='Toggle the state of this output'>Toggle</a>";
            }
            else if (thisChType == "counter") {
                thisState = thisState + "<a href='#' class='reset-counter-link' inputConnection='"+connectionNumber+"' title='Reset this counter to 0'>Reset</a>";
            }



            //$("#test-panel-table").jqGrid('setRowData', count, obj);
            $(selectorCount + " .test-panel-connection-link").text(connectionText);
            //console.log(selectorCount + " .test-panel-state");
            //console.log(thisState);
            $(selectorCount + " .test-panel-state").html(thisState);
            $(selectorCount + " .test-panel-sparkline").removeClass().addClass("test-panel-sparkline " + thisChType);
            count++;
        }
    }

    $('#test-panel-table .test-panel-sparkline').each(function(i) {
        var connectionText = data[i].connection;
        //console.log(data);
        var chartMinMax = sparklineMinMax(data[i].chType, data[i].devType);
        var sparklineOptions;
        if ($(this).hasClass("analogIn")) {
            sparklineOptions = sparklineAnalogInOptions;
            sparklineOptions.width = sparklineDataMap[i].length*5;
        } else if ($(this).hasClass("digitalIn")) {
            sparklineOptions = sparklineDigitalInOptions;        
            sparklineOptions.width = sparklineDataMap[i].length;
        } else if ($(this).hasClass("digitalOut")) {
            sparklineOptions = sparklineDigitalOutOptions;        
            sparklineOptions.width = sparklineDataMap[i].length;
        } else {
            sparklineOptions = sparklineAnalogInOptions;        
            sparklineOptions.width = sparklineDataMap[i].length*5;
        }
        sparklineOptions.chartRangeMin = chartMinMax.min;
        sparklineOptions.chartRangeMax = chartMinMax.max;
        $(this).sparkline(sparklineDataMap[i],  sparklineOptions);
    });
        

    restartScanning();
}


function handleMoreInfo(data) {
    $("#more-info-pane").html(data.html);
    
    $("#scan-bar").html(data.htmlScanning);

    currentSerialNumber = data.serial;
    highlightCurrentSerialNumber(currentSerialNumber);
    updateTabContent();

    callScan();
}

function handleSelectDevice(serialNumber) {
    if (serialNumber) {
        $.get("/devices/" + serialNumber, {}, handleMoreInfo, "json");
        $("#save-config-link").attr("href", "/config/exportConfigToFile/" + serialNumber);
        $(".timer-counter-config-link").attr("href", "/devices/timerCounterConfig/" + serialNumber);
        $("#device-summary-list").hide();
        $("#sm-tabs").hide();
        $("#tabs").show();   
    } else {
        //console.log("no serialNumber");
    }
}

function handleDeviceList(data) {
    $("#device-name-list").html(data.html);
    $("#device-summary-list").html(data.htmlSummaryList);
    if (currentSerialNumber) {
        highlightCurrentSerialNumber(currentSerialNumber);
    }
    if (data.usbOverride) {
        showTopMessage(data.usbOverride);
    }
}

function getDeviceList() {
    $.get("/devices/", {}, handleDeviceList, "json");
    $.get("/skymote/bridges", {}, smHandleBridgeList, "json");
}
  
/* Stuff For CloudDot Page */
function setupCloudDotLinks() {

    $("#username-field").live("blur", checkUsernameValidity);
    $("#apikey-field").live("blur", checkApikeyValidity);

    $("#user-form-submit").live("load", function() {
        console.log("#user-form-submit loaded");
        $(this).attr("disabled", "disabled");
    });
    $("#user-form").live("submit", function() {
        var username = $("#username-field").val();
        var apikey = $("#apikey-field").val();
        console.log("user-form submitted");
        saveCloudDotAccount(username, apikey);
        return false;    
    });
    $(".connect-to-clouddot-link").live("click", function() {
        var serialNumber = $(this).attr("device-serial");
        connectToClouddot(serialNumber);
        return false;
    });
    $(".disconnect-from-clouddot-link").live("click", function() {
        var serialNumber = $(this).attr("device-serial");
        disconnectFromClouddot(serialNumber);   
        return false;
    });
    $("#clouddot-api-key-example-link").live("click", function() {
        $("#clouddot-api-key-example").show();
        $(this).hide();
        return false;
    });
    $(".ping-link").live("click", function() {
        var serialNumber = $(this).attr("device-serial");
        pingFromCloudDot(serialNumber);   
        return false;
    });
}

function saveCloudDotAccount(username, apikey) {
    $.ajax({  
      type: "POST",  
      url: "/clouddot/update",  
      data: {username : username, apikey : apikey, serial : currentSerialNumber},
      success: function(data) {  
        console.log("saveCloudDotAccount success");
        $(".users-page-content").html(data.html);
        showCloudDotDisconnected(false);
        $("a.button").button();
      },
      dataType: "json" 
    });  
}

function showCloudDotConnected(showTop) {
    $("#clouddot-connected-div").show();
    $("#clouddot-disconnected-div").hide();
    if (showTop) {
        showTopMessage("Connected to CloudDot.");
    }
}

function showCloudDotDisconnected(showTop) {
    $("#clouddot-disconnected-div").show();
    $("#clouddot-connected-div").hide();
    if (showTop) {
        showTopMessage("Disconnected from CloudDot.");
    }
}

function handleCloudDotPing(data, textStatus, XMLHttpRequest) {
    var latestMessage = data.message;
    $("#ping-result-div").html(latestMessage);
    showTopMessage(data.message);
}

function pingFromCloudDot(serialNumber) {
    $.get("/clouddot/ping/"+serialNumber, {}, handleCloudDotPing, "json");
}

function handleCloudDotAjaxError(XMLHttpRequest, textStatus, errorThrown) {
    $('#username-field').removeClass("fieldWithNoErrors");
    $('#username-field').addClass("fieldWithErrors");
}

function handleCloudDotConnect(returnJson, textStatus, XMLHttpRequest) {
    if (returnJson.result == "connected") {
        showCloudDotConnected(true);
    } else {
        showCloudDotDisconnected(true);
    }
    return false;
}

function connectToClouddot(serial) {
    $.get("/clouddot/connect/"+serial, {}, handleCloudDotConnect, "json");
    
    return false;
}

function disconnectFromClouddot(serial) {
    $.get("/clouddot/disconnect/"+serial, {}, handleCloudDotConnect, "json");
    
    return false;
}

function handleUsernameApikeyCheck(data, textStatus) {
    if(data['username-valid'] == 1) {
      $('#username-field').removeClass("fieldWithErrors");
      $('#username-field').addClass("fieldWithNoErrors");
    }
    else {
      $('#username-field').removeClass("fieldWithNoErrors");
      $('#username-field').addClass("fieldWithErrors");
      cloudDotUsernameApiKeyError();
    }

    if (data['apikey-valid'] != undefined && data['apikey-valid'] == 1) {
      $('#apikey-field').removeClass("fieldWithErrors");
      $('#apikey-field').addClass("fieldWithNoErrors");
    }
    else if (data['apikey-valid'] != undefined && data['apikey-valid'] == 0) {
      $('#apikey-field').removeClass("fieldWithNoErrors");
      $('#apikey-field').addClass("fieldWithErrors");
      cloudDotUsernameApiKeyError();
    }

    if (data['username-valid'] == 1 && data['apikey-valid'] == 1) {
        cloudDotUsernameApiKeySuccess();
    }    
}

function cloudDotUsernameApiKeySuccess() {
    // Enable the CloudDot username submit button
    $("#user-form-submit").removeAttr("disabled");
    $("#clouddot-username-apikey-help").hide();
}

function cloudDotUsernameApiKeyError() {
    // Disable the CloudDot username submit button
    $("#user-form-submit").attr("disabled", "disabled");
    $("#clouddot-username-apikey-help").show();
}

function checkUsernameValidity() {
    var name = $('#username-field').attr('value');
    var apikey = $('#apikey-field').attr('value');

    if (apikey != null && apikey.length >0 ) {
        return checkApikeyValidity();
    }
    
    if(name == CloudDotLastUsername) {
      return false;
    }
    
    $.ajax({
            url : "/clouddot/check",
            dataType: 'json',
            success: handleUsernameApikeyCheck,
            error: handleCloudDotAjaxError,
            type: "GET",
            data: { label : "username", username : name, apikey : "crap" }
            });
            
    CloudDotLastUsername = name;
    
    return false;
}

function checkApikeyValidity() {
    var name = $('#username-field').attr('value');
    var apikey = $('#apikey-field').attr('value');
    
    if(name == CloudDotLastUsername && apikey == CloudDotLastApikey) {
      return false;
    }
    
    if( name != undefined && name != null && apikey != undefined && apikey != null) {
          
          $.ajax({
            url : "/clouddot/check",
            dataType: 'json',
            success: handleUsernameApikeyCheck,
            error: handleCloudDotAjaxError,
            data: { label : "apikey", username: name, apikey : apikey },
            type: "GET"
            });
            
          CloudDotLastUsername = name;
          CloudDotLastApikey = apikey;
    }
    
    return false;
}

function setupExitButton() {
    $("#exit-grounded a .ui-icon.ui-icon-circle-close").css({float : "left", "margin" : "2px 3px" });
    $("#exit-grounded a .ui-button-text").css({ "width" : "220px" });
    $("#exit-grounded a").button().bind("click", function() {
        $(this).find(".exit-grounded-text").text("Exiting");
       $.ajax({
            url : "/stop",
            dataType: 'json',
            success: function(returnJson) {
                if (returnJson.error == 0) {
                    showTopMessage("Exiting CloudDot Grounded. You may close this browser window.");
                    setTimeout(
                        finalCloseFunction, 2000);
                } else {
                    showTopMessage("Got error " + returnJson.error + " when exiting CloudDot Grounded.");
                }
            },
            error: function() {
                showTopMessage("Error when exiting CloudDot Grounded.");
            },
            type: "GET",
        });
    });
}

function finalCloseFunction() {
    // window.close doesn't work on Firefox
    window.close();
    $("#exit-grounded a .exit-grounded-text").text("You may now close this browser window");
    $("#exit-grounded a .ui-icon").hide();
}