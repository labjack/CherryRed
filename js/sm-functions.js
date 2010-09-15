function smRestartScanning() {
    if (refreshId != null) {
        clearTimeout(refreshId);
    }
    refreshId = setTimeout(smCallScan, 1000);
}

function smDialogDone() {
    $("#dialog").dialog("close");
    smCallScan();
    smRestartScanning();
}

function smCallScan() {
    $(".scanning-indicator").addClass("ui-icon ui-icon-bullet");
    $.ajax({
        url: "/skymote/scanBridge",
        data: {serial : currentSerialNumber},
        success: smHandleScan,
        dataType: "json"
    });
}

function smHandleScan(data) {
    //console.log("smHandleScan");
    //console.log(data);

    if (data.length == 0) {
        $("#sm-overview-tab, #scan-bar").html("Lost connection. Check the LabJack and <a href='/'>reload</a>.");
        smShowingOverviewTab == false;
        return;
    }

    $(".scanning-indicator").removeClass("ui-icon ui-icon-bullet");

    if (smShowingOverviewTab == false) {

        $("#sm-overview-tab .data-table").jqGrid({
          datatype: "local",
          height: "100%",
          colModel:[
               {name:'label',index:'label', width:250,  sortable:false},
               {name:'state',index:'state', width:250, sortable:false},
          ],
          multiselect: false,
          caption: "SkyMote Overview",
          beforeSelectRow : function() { return false; }
        });
        $('#sm-overview-tab .ui-jqgrid-hdiv').hide();

        var obj = { label : "Connected Motes" };
        obj.state = "<span class='test-panel-state'>" + data["Number of Connected Motes"] + "</span>";
        var count = 0;

        $("#overview-" + currentSerialNumber + " .data-table").jqGrid('addRowData', count, obj);

        for (var unitId in data["Connected Motes"]) {
            count = 0;
            //console.log(unitId);
            var moteData = data["Connected Motes"][unitId]["tableData"];
            for (var k in moteData) {
                //console.log(k);
                //console.log(moteData[k]);

                // Mike C. Need to account for more motes
                //var mapKey = unitId + "-" + k;
                var mapKey = k;
                sparklineDataMap[mapKey] = [];
                sparklineDataMap[mapKey].push(moteData[k].value);

                if (sparklineDataMap[mapKey].length > sparklineMaxPoints) {
                    sparklineDataMap[mapKey].splice(0,1);
                }


                obj = { label : moteData[k].connection, state : "<span class='test-panel-sparkline " + moteData[k].chType + "'></span>" + "<span class='test-panel-state'>" + moteData[k].state  + "</span>"};
                $("#overview-" + unitId + " .data-table").jqGrid('addRowData', count, obj);
                count++;
            }
        }


        smShowingOverviewTab = true;
    }
    else {

        $("#overview-" + currentSerialNumber + " .data-table tr#0 .test-panel-state").text(data["Number of Connected Motes"]);
        for (var unitId in data["Connected Motes"]) {
            var count = 0;
            // Do we have a place for this mote?
            $("#overview-" + unitId + " .name").text(data["Connected Motes"][unitId]["name"]);
            var moteData = data["Connected Motes"][unitId]["tableData"];
            if ($("#overview-" + unitId).length == 0) {
                $("#sm-overview-tab").append(data["Connected Motes"][unitId]["html"]);
                $("#overview-" + unitId + " .data-table").jqGrid({
                  datatype: "local",
                  height: "100%",
                  colModel:[
                       {name:'label',index:'label', width:250,  sortable:false},
                       {name:'state',index:'state', width:250, sortable:false},
                  ],
                  multiselect: false,
                  caption: "SkyMote Overview",
                  beforeSelectRow : function() { return false; }
                });
                $('#sm-overview-tab .ui-jqgrid-hdiv').hide();
                for (var k in moteData) {
                    obj = { label : moteData[k].connection, state : "<span class='test-panel-state'>" + moteData[k].state  + "</span>"};
                    $("#overview-" + unitId + " .data-table").jqGrid('addRowData', count, obj);
                    count++;
                }



            }
            else {
                for (var k in moteData) {

                    // Mike C. Need to account for more motes
                    //var mapKey = unitId + "-" + k;
                    var mapKey = k;
                    sparklineDataMap[mapKey].push(moteData[k].value);

                    if (sparklineDataMap[mapKey].length > sparklineMaxPoints) {
                        sparklineDataMap[mapKey].splice(0,1);
                    }


                    var selectorCount = "tr#" + count;
                    $("#overview-" + unitId + " " + selectorCount + " .test-panel-state").html(moteData[k].state);
                    count++;
                }
            }
        }


    }


        $('#sm-overview-tab .test-panel-sparkline').each(function(i) {
        //var connectionText = data[i].connection;
        //console.log(data);

        //var chartMinMax = sparklineMinMax(data[i].chType, data[i].devType);
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

        // LQI sparklines get a normal range
        if ($(this).hasClass("lqi")) {
            sparklineOptions = sparklineLQIOptions;
            sparklineOptions.width = sparklineDataMap[i].length*5;
        }
        // So does Vbatt
        else if ($(this).hasClass("vbatt")) {
            sparklineOptions = sparklineVbattOptions;
            sparklineOptions.width = sparklineDataMap[i].length*5;
        }

        //sparklineOptions.chartRangeMin = chartMinMax.min;
        //sparklineOptions.chartRangeMax = chartMinMax.max;
        $(this).sparkline(sparklineDataMap[i],  sparklineOptions);
    });


    smRestartScanning();
}

function smHandleMoreInfo(data) {

    $("#sm-overview-tab").html(data.html);

    $("#scan-bar").html(data.htmlScanning);

    currentSerialNumber = data.serial;
    highlightCurrentSerialNumber(currentSerialNumber);

    smCallScan();

}

function smHandleSelectBridge(bridgeSerialNumber) {
    $.get("/skymote/" + bridgeSerialNumber, {}, smHandleMoreInfo, "json");
    $("#device-summary-list").hide();
    $("#tabs").hide();
    $("#sm-tabs").show();
}

function smHandleBridgeList(data) {
    $("#device-name-list").append(data.html);
    $("#device-summary-list").append(data.htmlSummaryList);
    
    $("#bridge-name-list").html("");
    $("#bridge-summary-list").html("");
    
    if (currentSerialNumber) {
        highlightCurrentSerialNumber(currentSerialNumber);
    }
}  

function setupConfigureMoteLinks() {
    $(".configure-mote").live("click", function() {
        //console.log("setupConfigureMoteLinks");
        var targetUrl = $(this).attr("href");
        $.get(targetUrl, function(returnJson) {
            $("#dialog").html(returnJson.html);
            $("#update-rate-slider").slider({
                 range: "min",
                    value:returnJson.moteCheckinInterval,
                    min: 1,
                    max: 60,
                    step: 1,
                    slide: function(event, ui) {
                        $("#update-rate-seconds").val(ui.value);
                    }
                });
            $("#update-rate-seconds").val($("#update-rate-slider").slider("value")).blur(function() {
                var newValue = $(this).val();
                if (newValue >=1 && newValue <= 60) {
                    $("#update-rate-slider").slider("option", "value", $(this).val());
                }
            });

            $("#mote-config-form").submit(function() {
                var newValue = $("#update-rate-seconds").val();
                console.log(newValue);
                if (newValue >=1 && newValue <= 60) {
                    $.get("/skymote/updateMoteSettings", 
                        {
                            serial    : returnJson.bridgeSerial, 
                            unitId    : returnJson.moteUnitId,
                            name      : $("#edit-name").val(),
                            newUnitId : $("#edit-unitid").val(),
                            checkinInterval: newValue
                        }, function (data) { console.log("returned from updateMoteSettings"); return true;}, "json");
                }
                smDialogDone();
                return false;
            });
    
            
            
            
            $("#edit-name").val(returnJson.moteName);
            $("#edit-unitid").val(returnJson.moteUnitId);
            $("#dialog").dialog('option', 'title', returnJson.formTitle);
            $("#dialog").dialog('option', 'width', 525);
            $("#dialog").dialog('option', 'height', 375);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    $("#mote-config-form").submit();
                },
                "Cancel": smDialogDone
            });
            $("#dialog").dialog('open');
        });
        return false;
    });
}

