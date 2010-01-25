    
var refreshId = null;
var currentSerialNumber = null;

var showingTestPanel = false;

var sparklineDataMap = {};
var sparklineMaxPoints = 22;
var sparklineAnalogInOptions = {height: "15px", minSpotColor: false, maxSpotColor: false, spotColor: "#CC0000", lineColor: "#004276", fillColor: "#E6F3FF" };
var sparklineDigitalInOptions = {type:'bar', height: "15px", barColor: "#004276" };
var sparklineDigitalOutOptions = {type:'bar', height: "15px", barColor: "#CC0000" };


$(document).ready(function() {
    $("#tabs").tabs();
    setupTestPanelConnectionLinks();
    setupDialog();
    getDeviceList();
});

function stopScanning() {
    console.log(refreshId);
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

function setupTestPanelConnectionLinks() {
    $(".test-panel-connection-link").live("click", function(e){
        //console.log(e.target);
        stopScanning();
        $("#dialog").empty();
        $("#u3-connection-dialog").jqote().appendTo($("#dialog"));
        $("#u3-connection-dialog-tabs").tabs();
        $("#dialog").dialog('option', 'title', $(this).text());
        $("#dialog").dialog('open');
        return false;
    });
}

function sparklineMinMax(sparklineType) {
    minMax = {};
    switch (sparklineType) {
        case "analogIn":
            minMax.min = 0;
            minMax.max = 3.3;
            break;
        case "digitalIn":
        case "digitalOut":
            minMax.min = 0;
            minMax.max = 1;
            break;
        case "internalTemp":
            minMax.min = 20;
            minMax.max = 35;
            break;
        default:
            minMax.min = 0;
            minMax.max = 5;
            break;
    }
    return minMax;
}


function callScan() {
    $.get("/devices/scan", {serial : currentSerialNumber}, handleScan, "json");
}

function handleScan(data) {
    
    if (showingTestPanel == false) {
        
        $("#test-panel-table").jqGrid({
          datatype: "local",
          height: "100%",
             colNames:['Connection','State'],
             colModel:[
               {name:'connection',index:'connection', width:250,  sortable:false},
               {name:'state',index:'state', width:250, sortable:false}
             ],
             multiselect: false,
             caption: "Test Panel"
        });


        var count = 0;
        for (var d in data) {
            var thisConnection = data[d].connection;
            var thisState = data[d].state;
            var thisValue = data[d].value;
            var obj = { connection : thisConnection, state: thisState };
            $("#test-panel-table").jqGrid('addRowData', count, obj);
            count++;
            sparklineDataMap[thisConnection] = [];
        }
        showingTestPanel = true;

    }
    var count = 0;
    for (var d in data) {          
        var thisConnection = data[d].connection;
        var thisState = data[d].state;
        var thisValue = data[d].value;
        var thisChType = data[d].chType;
        sparklineDataMap[thisConnection].push(thisValue);
        
        if (sparklineDataMap[thisConnection].length > sparklineMaxPoints) {
            sparklineDataMap[thisConnection].splice(0,1);
        }
        var obj = { connection : "<a href='#' class='test-panel-connection-link'>"+thisConnection+"</a>", state: "<span class='test-panel-sparkline " + thisChType + "'></span>" + "<span class='test-panel-state'>"+thisState + "</span>" };
        $("#test-panel-table").jqGrid('setRowData', count, obj);
        count++;
    }

    $('.test-panel-sparkline').each(function(i) {
        var thisConnection = data[i].connection;
        var chartMinMax = sparklineMinMax(data[i].chType);
        var sparklineOptions;
        if ($(this).hasClass("analogIn")) {
            sparklineOptions = sparklineAnalogInOptions;
            sparklineOptions.width = sparklineDataMap[thisConnection].length*5;
        } else if ($(this).hasClass("digitalIn")) {
            sparklineOptions = sparklineDigitalInOptions;        
            sparklineOptions.width = sparklineDataMap[thisConnection].length;
        } else if ($(this).hasClass("digitalOut")) {
            sparklineOptions = sparklineDigitalOutOptions;        
            sparklineOptions.width = sparklineDataMap[thisConnection].length;
        } else {
            sparklineOptions = sparklineAnalogInOptions;        
            sparklineOptions.width = sparklineDataMap[thisConnection].length*5;
        }
        sparklineOptions.chartRangeMin = chartMinMax.min;
        sparklineOptions.chartRangeMax = chartMinMax.max;
        $(this).sparkline(sparklineDataMap[thisConnection],  sparklineOptions);
    });
        

    restartScanning();
}

function handleMoreInfo(data) {
    $("#more-info-pane").empty();
    $("#more-info-template").jqote(data).appendTo($("#more-info-pane"));

    currentSerialNumber = data.serial;

    callScan();
}

function handleSelectDevice(event, ui) {
    var serialNumber = ui.selected.id;
    $.get("/devices/" + serialNumber, {}, handleMoreInfo, "json");
      
    $("#tabs").show();  
}
  
function handleDeviceList(data) {
    for (var d in data) {
    var obj = { name: data[d], serial : d };
        $("#device-template").jqote(obj).appendTo($("#device-name-list"));
    }
    $("#device-name-list").selectable({
        selected: function(event, ui) { 
            $(ui.selected).addClass("ui-helper-reset ui-widget-header");
            handleSelectDevice(event, ui);
        }
    });
}
  
  
function getDeviceList() {
    $.get("/devices/", {}, handleDeviceList, "json");
}
  
