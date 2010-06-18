    
var refreshId = null;
var logFileRefreshId = null;
var currentSerialNumber = null;

var showingTestPanel = false;

var sparklineDataMap = {};
var sparklineMaxPoints = 22;
var sparklineAnalogInOptions = {height: "15px", minSpotColor: false, maxSpotColor: false, spotColor: "#A20000", lineColor: "#004276", fillColor: "#E6F3FF" };
var sparklineDigitalInOptions = {type:'bar', height: "16px", barColor: "#004276" };
var sparklineDigitalOutOptions = {type:'bar', height: "16px", barColor: "#A20000" };


$(document).ready(function() {
    $("#tabs").tabs();
    setupHashChange();    
    setupTestPanelConnectionLinks();
    setupRenameLinks();
    setupStopLoggingLinks();
    setupDialog();
    setupLogCheckboxes();
    setupLogFileScanning();
    setupSupportTab();
    getDeviceList();
    updateLogBar();
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
    $("#test-panel-table").empty();
    // In jQuery 1.4, use e.getState( "url" );
    var serialNumber = e.getState( "d" );
    highlightCurrentSerialNumber(serialNumber);

    //console.log(" urlHashChange d = " + serialNumber );
    if (serialNumber) {
        handleSelectDevice(serialNumber);
    } else {
        $("#tabs").hide();
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
    refreshId = setTimeout(callScan, 1000);
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
        var textVal = $(this).closest("tr").addClass("ui-state-highlight").find(".test-panel-connection-link").text();
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
    $.ajax({
        url: "/logs/logFileList", 
        success: handleLogFileScan, 
        dataType: "string"
    });
}

function handleLogFileScan(data) {
    $("#log-wrapper").html(data);
}

function setupSupportTab() {
    var $tabs = $("#tabs").tabs();
    $tabs.bind( "tabsselect", function(event, ui) {
//        var selected = $tabs.tabs('option', 'selected');
//            console.log(selected);
        if (ui.index == 3) {
            $.get("/devices/support/" + currentSerialNumber, {}, function(data)  {$("#support-tab").html(data); });
        } else if(ui.index == 1) {
            $.get("/config/filelist/" + currentSerialNumber, {}, function(data)  {$("#config-file-list").html(data); });
        }
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
            restartScanning();
            $("#dialog").dialog('close');
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
    else if (inputInfoJson.device.devType == 6) {
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
        $("#u6-connection-dialog-tabs").tabs();
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
            
            
            var obj = { connection : "<a href='#' class='test-panel-connection-link' inputConnection='"+connectionNumber+"' title='Configure " + connectionText + "'>"+connectionText+"</a>", state: "<span class='test-panel-sparkline " + thisChType + "'></span>" + "<span class='test-panel-state'>"+thisState + "</span>", log: "<input type='checkbox' class='log-checkbox' />"};
            if (thisLogging) {
                obj.log = "<input type='checkbox' class='log-checkbox' checked='yes' />";
            }
            if (connectionText == "Internal Temperature") {
                obj.connection = connectionText; // No link
            }

            $("#test-panel-table").jqGrid('addRowData', count, obj);
            highlightCheckedCheckboxes();
            count++;
        }
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
            
            

            //$("#test-panel-table").jqGrid('setRowData', count, obj);
            $(selectorCount + " .test-panel-connection-link").text(connectionText);
            //console.log(selectorCount + " .test-panel-state");
            //console.log(thisState);
            $(selectorCount + " .test-panel-state").html(thisState);
            $(selectorCount + " .test-panel-sparkline").removeClass().addClass("test-panel-sparkline " + thisChType);
            count++;
        }
    }

    $('.test-panel-sparkline').each(function(i) {
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

    callScan();
}

function handleSelectDevice(serialNumber) {
    if (serialNumber) {
        $.get("/devices/" + serialNumber, {}, handleMoreInfo, "json");
        $("#save-config-link").attr("href", "/config/exportConfigToFile/" + serialNumber);
        $("#device-summary-list").hide();
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
}
  
  
function getDeviceList() {
    $.get("/devices/", {}, handleDeviceList, "json");
}
  
