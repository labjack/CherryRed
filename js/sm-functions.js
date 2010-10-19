function formatMyDate(date){
    //return ""+date;
    var dateStr = date.getMonth()+"/"+date.getDay()+"/"+date.getFullYear()+" ";
    
    var timeStr = date.getHours()+":";
    
    if(date.getMinutes() < 10) {
        timeStr = timeStr+"0"+date.getMinutes()+":";
    } else {
        timeStr = timeStr+date.getMinutes()+":";
    }
    Converting the OpenSSH private key to Putty format
    if (date.getSeconds() < 10) {
        timeStr = timeStr+"0"+date.getSeconds();
    } else {
        timeStr = timeStr+date.getSeconds();
    }
    
    return dateStr+timeStr;
}

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
               {name:'state',index:'state', width:250,  sortable:false}
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
                var mapKey = unitId + "-" + k;
                //console.log(unitId + "-" + k);
                //var mapKey = k;
                sparklineDataMap[mapKey] = [];
                sparklineDataMap[mapKey].push(moteData[k].value);

                if (sparklineDataMap[mapKey].length > sparklineMaxPoints) {
                    sparklineDataMap[mapKey].splice(0,1);
                }


                obj = { label : moteData[k].connection, state : "<span class='test-panel-sparkline " + moteData[k].chType + "' rowIndex='" + count + "'></span>" + "<span class='test-panel-state'>" + moteData[k].state  + "</span>"};
                $("#overview-" + unitId + " .data-table").jqGrid('addRowData', count, obj);
                count++;
            }
        }


        smShowingOverviewTab = true;
    }
    else {

        $("#overview-" + currentSerialNumber + " .data-table tr#0 .test-panel-state").text(data["Number of Connected Motes"]);
        
        // Set the text "(Disconnected)" for lost motes.
        if(data["Number of Connected Motes"] == 0) {
            $(".rapid-mode").text("(Disconnected)");
        } else {
            var t;
            $(".rapid-mode").each( function(index, elem) {
                t = $(elem).parent().attr('unitid');
                if( data["Connected Motes"][t] == undefined ) {
                    $(elem).text("(Disconnected)");
                }
            });
        }
        
        for (var unitId in data["Connected Motes"]) {
            var count = 0;
            // Do we have a place for this mote?
            $("#overview-" + unitId + " .name").text(data["Connected Motes"][unitId]["name"]);
            if (data["Connected Motes"][unitId]["inRapidMode"]) {
                $("#overview-" + unitId + " .rapid-mode").text("(Rapid mode, updating once per second)");            
            } else if( data["Connected Motes"][unitId]["missed"] && data["Connected Motes"][unitId]["missed"] != 0 ) {
                $("#overview-" + unitId + " .rapid-mode").text("(mote missed "+data["Connected Motes"][unitId]["missed"]+" communications.)");
            } else {
                $("#overview-" + unitId + " .rapid-mode").text("");            
            }
            
            if(data["Connected Motes"][unitId]["lastComm"] == -1) {
                $("#overview-" + unitId + " .last-comm-text").text("Never");
            } else {
                var d = new Date( data["Connected Motes"][unitId]["lastComm"]*1000 );
                $("#overview-" + unitId + " .last-comm-text").text(formatMyDate(d));
            }
            
            var moteData = data["Connected Motes"][unitId]["tableData"];
            if ($("#overview-" + unitId).length == 0) {
                $("#sm-overview-tab").append(data["Connected Motes"][unitId]["html"]);
                $("#overview-" + unitId + " .data-table").jqGrid({
                  datatype: "local",
                  height: "100%",
                  colModel:[
                       {name:'label',index:'label', width:250,  sortable:false},
                       {name:'state',index:'state', width:250,  sortable:false}
                  ],
                  multiselect: false,
                  caption: "SkyMote Overview",
                  beforeSelectRow : function() { return false; }
                });
                $('#sm-overview-tab .ui-jqgrid-hdiv').hide();
                for (var k in moteData) {
                    var connectionClass = ""
                    if( moteData[k].connection == "Tx Link Quality" || moteData[k].connection == "Tx Link Quality") {
                        if(moteData[k].value > 100) {
                            connectionClass = "good-quality"
                        } else if(moteData[k].value <= 100 && moteData[k].value >= 60) {
                            connectionClass = "warn-quality"
                        } else {
                            connectionClass = "bad-quality"
                        }
                    }
                    obj = { label : moteData[k].connection, state :  "<span class='test-panel-sparkline " + moteData[k].chType + "' rowIndex='" + count + "'></span>" + "<span class='test-panel-state "+connectionClass+"'>" + moteData[k].state  + "</span>"};
                    $("#overview-" + unitId + " .data-table").jqGrid('addRowData', count, obj);
                    count++;
                }
            }
            else {
                for (var k in moteData) {

                    // Mike C. Need to account for more motes
                    var mapKey = unitId + "-" + k;
                    //console.log(unitId + "-" + k);
                    //var mapKey = k;
                    if (sparklineDataMap[mapKey] == undefined) {
                        sparklineDataMap[mapKey] = [ moteData[k].value ];
                    } else {
                        sparklineDataMap[mapKey].push(moteData[k].value);
                    }

                    if (sparklineDataMap[mapKey].length > sparklineMaxPoints) {
                        sparklineDataMap[mapKey].splice(0,1);
                    }

                    var connectionClass = ""
                    if( moteData[k].connection == "Tx Link Quality" || moteData[k].connection == "Rx Link Quality") {
                        if(moteData[k].value > 100) {
                            connectionClass = "good-quality"
                        } else if(moteData[k].value <= 100 && moteData[k].value >= 60) {
                            connectionClass = "warn-quality"
                        } else {
                            connectionClass = "bad-quality"
                        }
                    }

                    var selectorCount = "tr#" + count;
                    $("#overview-" + unitId + " " + selectorCount + " .test-panel-state").html(moteData[k].state);
                    $("#overview-" + unitId + " " + selectorCount + " .test-panel-state").attr("class", "test-panel-state "+connectionClass);
                    count++;
                }
            }
        }


    }


        $('#sm-overview-tab .test-panel-sparkline').each(function(i) {
         //console.log(i);
         
         var rowIndex = $(this).attr("rowindex");
         
         var moteUnitId = $(this).closest(".moteoverview").attr("unitid");
         var moteKey = moteUnitId + "-" + rowIndex;
        //var connectionText = data[i].connection;
        //console.log(data);

        //var chartMinMax = sparklineMinMax(data[i].chType, data[i].devType);
        
        if (sparklineDataMap[moteKey] != undefined) {
            var sparklineOptions;
            if ($(this).hasClass("analogIn")) {
                sparklineOptions = sparklineAnalogInOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length*5;
            } else if ($(this).hasClass("digitalIn")) {
                sparklineOptions = sparklineDigitalInOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length;
            } else if ($(this).hasClass("digitalOut")) {
                sparklineOptions = sparklineDigitalOutOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length;
            } else {
                sparklineOptions = sparklineAnalogInOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length*5;
            }
    
            // LQI sparklines get a normal range
            if ($(this).hasClass("lqi")) {
                sparklineOptions = sparklineLQIOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length*5;
            }
            // So does Vbatt
            else if ($(this).hasClass("vbatt")) {
                sparklineOptions = sparklineVbattOptions;
                sparklineOptions.width = sparklineDataMap[moteKey].length*5;
            }
    
            //sparklineOptions.chartRangeMin = chartMinMax.min;
            //sparklineOptions.chartRangeMax = chartMinMax.max;
            $(this).sparkline(sparklineDataMap[moteKey],  sparklineOptions);
        }
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
    $("#exit-grounded").hide();
    $("#tabs").hide();
    $("#sm-tabs").show();
}

function smSetupTabSelect() {
    var $tabs = $("#sm-tabs").tabs();
    $tabs.bind("tabsselect", function(event, ui) {
        updateSmTabContent(ui.index);
    });
}

function updateSmTabContent(tabIndex) {
    if (tabIndex == undefined) {
        var $tabs = $("#tabs").tabs();
        tabIndex = $tabs.tabs('option', 'selected');
    }
    
    // Firmware tab
    if (tabIndex == 1) {
        $.get("/skymote/listFirmware", {}, 
            function(data) {
                $("#sm-firmware-tab").html(data.html);
                $("#sm-firmware-tab .firmware-list a").button();
            }
        );
    }
    else if (tabIndex == 2) {
        stopScanning();
        $.get("/skymote/support", {}, 
            function(data) {
                $("#sm-support-tab").html(data.html);
                $("#read-modbus-register-form").submit(smSubmitReadRegisterForm);
                $(".resend-link").live("click", resendCommand);
            }
        );
    } else if (tabIndex == 0) {
        smRestartScanning();
    }
    
    //console.log(tabIndex);
}

function smSubmitReadRegisterForm() {
    var addr = $("#addr").val();
    var numReg = $("#numReg").val();
    var format = $("#format").val();
    var unitId = $("#unitId").val();
    
    $.get("/skymote/readRegister/"+currentSerialNumber, 
          { addr : addr, numReg : numReg, format : format, unitId : unitId },
          function(data) {
            if(data.error != undefined) {
                $("#read-results-list").prepend(data.error);
            } else {
                $("#read-results-list").prepend(data.html);
                
            }
          }
    );
    
    return false;
}

function resendCommand(){
    $("#addr").val( $(this).attr('addr') );
    $("#numReg").val( $(this).attr('numReg') );
    $("#format").val( $(this).attr('format') );
    $("#unitId").val( $(this).attr('unitId') );
    
    smSubmitReadRegisterForm();
    
    return false;
}

function smSetupFirmwareButtons() {
    $("#sm-firmware-tab .firmware-list a").live("click", function() {
        stopScanning();
        showTopMessage("Upgrading firmware");
        $("#scan-bar").text("");
        $.ajax({
            url : "/skymote/doFirmwareUpgrade/" + currentSerialNumber,
            dataType: 'json',
            data : { unitId : $(this).attr("unitId"), fwFile : $(this).attr("fwFile") },
            success: function(returnJson) {
                if (returnJson.error == 0) {
                    showTopMessage(returnJson.string);
                    setTimeout(smFirmwareStatusCheck, 1000);
                } else {
                    showTopMessage("Received error " +  returnJson.error + " when upgrading firmware: " + returnJson.string);
                }
            },
            error: function() {
                showTopMessage("Error when upgrading firmware.");
            },
            type: "GET"
        });
        return false;
    });
}

function smFirmwareStatusCheck() {
        $.ajax({
            url : "/skymote/firmwareUpgradeStatus/" + currentSerialNumber,
            dataType: 'json',
            success: function(returnJson) {
                showTopMessage(returnJson.message);
                if (returnJson.inProgress) {
                    setTimeout(smFirmwareStatusCheck, 1000);
                } else {
                    smCallScan();
                }
            },
            error: function() {
                showTopMessage("Error when upgrading firmware.");
            },
            type: "GET"
        });
}


function smHandleBridgeList(data) {
    $("#device-name-list").append(data.html);
    // Since we're only appending, hide any "<h2>No devices...</h2>
    $("#device-summary-list").find("h2").hide()
    $("#device-summary-list").append(data.htmlSummaryList);
    
    $("#bridge-name-list").html("");
    $("#bridge-summary-list").html("");
    
    if (currentSerialNumber) {
        highlightCurrentSerialNumber(currentSerialNumber);
    }
}  

function smSetupConfigureMoteLinks() {
    $(".configure-mote").live("click", function() {
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
                //console.log(newValue);
                if (newValue >=1 && newValue <= 60) {
                
                    var oldUnitId = returnJson.moteUnitId;
                    var newUnitId = $("#edit-unitid").val();
                    if (oldUnitId != newUnitId) {
                        $("#overview-" + oldUnitId).remove();
                    }
                
                    $.get("/skymote/updateMoteSettings", 
                        {
                            serial    : returnJson.bridgeSerial, 
                            unitId    : oldUnitId,
                            name      : $("#edit-name").val(),
                            newUnitId : newUnitId,
                            checkinInterval: newValue
                        }, function (data) { return true;}, "json");
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

function smSetupConfigureBridgeLinks() {
    $(".configure-bridge").live("click", function() {
        var targetUrl = $(this).attr("href");
        $.get(targetUrl, function(returnJson) {
            $("#dialog").html(returnJson.html);

            $("#bridge-config-form").submit(function() {
                var newName = $("#edit-name").val();
                var enabled = 0;
                
                if( $("#network-password-enabled").is(':checked') ) {
                    enabled = 1;
                }
                
                var password = $("#network-password").val();
                
                $.get("/skymote/updateBridgeSettings", 
                    {
                        serial    : returnJson.bridgeSerial, 
                        name      : newName,
                        enablePassword : enabled,
                        password: password
                    }, function (data) { return true;}, "json");
                
                smDialogDone();
                return false;
            });
            
            $("#dialog").dialog('option', 'title', returnJson.formTitle);
            $("#dialog").dialog('option', 'width', 525);
            $("#dialog").dialog('option', 'height', 375);
            $("#dialog").dialog('option', 'buttons', { 
                "Save": function() {
                    $("#bridge-config-form").submit();
                },
                "Cancel": smDialogDone
            });
            $("#dialog").dialog('open');
        });
        return false;
    });
}

