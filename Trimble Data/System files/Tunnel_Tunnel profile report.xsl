<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt">

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="yes" encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl6" select="concat('#0', $DecPt, '000000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="Pi" select="3.14159265358979323846264"/>
<xsl:variable name="halfPi" select="$Pi div 2.0"/>

<xsl:variable name="DegreesSymbol" select="'.'"/>
<xsl:variable name="MinutesSymbol" select="''"/>
<xsl:variable name="SecondsSymbol" select="''"/>

<xsl:variable name="fileExt" select="'htm'"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->
<xsl:variable name="userField1" select="'overallStnTol|Station tolerance|String'"/>
<xsl:variable name="overallStnTol" select="'Field setting'"/>
<xsl:variable name="userField2" select="'overallOverbreakTol|Overbreak tolerance|String'"/>
<xsl:variable name="overallOverbreakTol" select="'Field setting'"/>
<xsl:variable name="userField3" select="'overallUnderbreakTol|Underbreak tolerance|String'"/>
<xsl:variable name="overallUnderbreakTol" select="'Field setting'"/>

<!-- Define key to speed up searching -->
<xsl:key name="obsPointID-search" match="//JOBFile/FieldBook/PointRecord" use="@ID"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>

  <title>Tunnel Profile Report</title>
  <h2>Tunnel Profile Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    BODY, TABLE, TD
    {
      font-size:16px;
    }
    CAPTION
    {
      font-size:18px;
    }
  </style>

  <head>
  </head>

  <body>

    <xsl:call-template name="StartTable">
      <xsl:with-param name="includeBorders" select="'false'"/>
      <xsl:with-param name="width" select="50"/>
    </xsl:call-template>
    
      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Tunnel name:'"/>
        <xsl:with-param name="Val" select="JOBFile/FieldBook/TunnelCrossSectionRecord[1]/TunnelName"/>
      </xsl:call-template>

      <xsl:call-template name="OutputSingleElementTableLine">
        <xsl:with-param name="Hdr" select="'Date:'"/>
        <xsl:with-param name="Val">
          <xsl:call-template name="formattedDateString">
            <xsl:with-param name="date" select="substring-before(JOBFile/FieldBook/TunnelCrossSectionRecord[1]/@TimeStamp, 'T')"/>
          </xsl:call-template>
        </xsl:with-param>
      </xsl:call-template>

    <xsl:call-template name="EndTable"/>

    <xsl:call-template name="BlankLine"/>
    
    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />

  </body>
  </html>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">

  <xsl:for-each select="TunnelCrossSectionRecord">
    <xsl:variable name="stn" select="Station"/>
    <xsl:variable name="tunnelName" select="TunnelName"/>
    <xsl:variable name="tunnelStnTol">
      <xsl:choose>
        <xsl:when test="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/StationTolerance">
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/StationTolerance"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/ScanStationTolerance"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="tunnelOverbreakTol">
      <xsl:choose>
        <xsl:when test="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/OverbreakTolerance">
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/OverbreakTolerance"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/ScanOverbreakTolerance"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="tunnelUnderbreakTol">
      <xsl:choose>
        <xsl:when test="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/UnderbreakTolerance">
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/UnderbreakTolerance"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="//JOBFile/FieldBook/TunnelSettingsRecord[TunnelName = $tunnelName]/ScanUnderbreakTolerance"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <xsl:if test="count(following-sibling::TunnelCrossSectionRecord[Station = $stn]) = 0"> <!-- Only output the details for the last profile taken at this station -->
      <xsl:variable name="stnTol">
        <xsl:choose>
          <xsl:when test="string(number($overallStnTol)) = 'NaN'">
            <xsl:value-of select="$tunnelStnTol * $DistConvFactor"/>   <!-- Use the cross-section record station tolerance -->
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$overallStnTol"/>     <!-- Use the specified station tolerance as an over-ride -->
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="overCutTol">
        <xsl:choose>
          <xsl:when test="string(number($overallOverbreakTol)) = 'NaN'">
            <xsl:value-of select="$tunnelOverbreakTol * $DistConvFactor"/>   <!-- Use the cross-section record station tolerance -->
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$overallOverbreakTol"/> <!-- Use the specified station tolerance as an over-ride -->
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="underCutTol">
        <xsl:choose>
          <xsl:when test="string(number($overallUnderbreakTol)) = 'NaN'">
            <xsl:value-of select="$tunnelUnderbreakTol * $DistConvFactor"/>   <!-- Use the cross-section record station tolerance -->
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$overallUnderbreakTol"/> <!-- Use the specified station tolerance as an over-ride -->
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:call-template name="StartTable">
        <xsl:with-param name="caption">
          <xsl:variable name="stationStr">
            <xsl:choose>
              <xsl:when test="EquatedStation">
                <xsl:call-template name="FormatStationVal">
                  <xsl:with-param name="stationVal" select="EquatedStation/Station"/>
                  <xsl:with-param name="zoneVal" select="EquatedStation/Zone"/>
                </xsl:call-template>
              </xsl:when>
              <xsl:otherwise>
                <xsl:call-template name="FormatStationVal">
                  <xsl:with-param name="stationVal" select="Station"/>
                </xsl:call-template>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:variable>
          <xsl:value-of select="concat('Station: ', $stationStr)"/>
        </xsl:with-param>
        <xsl:with-param name="includeBorders" select="'Yes'"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="''"/>
        <xsl:with-param name="Val2" select="'Number'"/>
        <xsl:with-param name="Val3" select="'Tolerance Value'"/>
        <xsl:with-param name="hdrLine" select="'true'"/>
      </xsl:call-template>

      <xsl:variable name="profilePoints">
        <xsl:for-each select="TunnelPointDeltaRecord">
          <xsl:variable name="obsID" select="ObservationID"/>
          <xsl:variable name="deletedPt" select="/JOBFile/FieldBook/PointRecord[@ID = $obsID]/Deleted"/>

          <xsl:if test="$deletedPt = 'false'">  <!-- Referenced point is not deleted -->
            <!-- Add point to node set variable if it is the first occurence of this point (to maintain the order) -->
            <xsl:if test="count(preceding-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) = 0">
              <!-- Now we want to make sure that we use the last set of values available for a point -->
              <xsl:choose>
                <xsl:when test="count(following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) &gt; 0">
                  <!-- Get the details for the last deltas record for this point -->
                  <xsl:for-each select="following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')][last()]">
                    <xsl:call-template name="AssignNodeSetValues">
                      <xsl:with-param name="stnTol" select="$stnTol"/>
                      <xsl:with-param name="overCutTol" select="$overCutTol"/>
                      <xsl:with-param name="underCutTol" select="$underCutTol"/>
                    </xsl:call-template>
                  </xsl:for-each>
                </xsl:when>
                <xsl:otherwise>  <!-- This is the one and only delta record for this point -->
                  <xsl:call-template name="AssignNodeSetValues">
                    <xsl:with-param name="stnTol" select="$stnTol"/>
                    <xsl:with-param name="overCutTol" select="$overCutTol"/>
                    <xsl:with-param name="underCutTol" select="$underCutTol"/>
                  </xsl:call-template>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:if>
          </xsl:if>
        </xsl:for-each>
      </xsl:variable>

      <xsl:variable name="profilePtsCount" select="count(msxsl:node-set($profilePoints)/TunnelPointDeltaRecord)"/>

      <xsl:variable name="inTolPtsCount" select="count(msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[(undercutExceeded = 'false') and (overcutExceeded = 'false') and (stnTolExceeded = 'false')])"/>

      <xsl:variable name="undercutPtsCount" select="count(msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[undercutExceeded = 'true'])"/>
      <xsl:variable name="overcutPtsCount" select="count(msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[overcutExceeded = 'true'])"/>
      <xsl:variable name="stnTolPtsCount" select="count(msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[stnTolExceeded = 'true'])"/>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of tunnel profile points'"/>
        <xsl:with-param name="Val2" select="$profilePtsCount"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of out of tolerance points'"/>
        <xsl:with-param name="Val2" select="$profilePtsCount - $inTolPtsCount"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of in tolerance points'"/>
        <xsl:with-param name="Val2" select="$inTolPtsCount"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of overbreak points'"/>
        <xsl:with-param name="Val2" select="$overcutPtsCount"/>
        <xsl:with-param name="Val3" select="format-number($overCutTol, $DecPl3, 'Standard')"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of underbreak points'"/>
        <xsl:with-param name="Val2" select="$undercutPtsCount"/>
        <xsl:with-param name="Val3" select="format-number($underCutTol, $DecPl3, 'Standard')"/>
      </xsl:call-template>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="Val1" select="'Number of points outside station tolerance'"/>
        <xsl:with-param name="Val2" select="$stnTolPtsCount"/>
        <xsl:with-param name="Val3" select="format-number($stnTol, $DecPl3, 'Standard')"/>
      </xsl:call-template>

      <xsl:call-template name="EndTable"/>
      <xsl:call-template name="BlankLine"/>

    </xsl:if>
  </xsl:for-each>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* Assign Node Set Values ******************* -->
<!-- **************************************************************** -->
<xsl:template name="AssignNodeSetValues">
  <xsl:param name="stnTol"/>
  <xsl:param name="overCutTol"/>
  <xsl:param name="underCutTol"/>

  <xsl:copy>
    <xsl:copy-of select="*"/>

    <xsl:element name="undercutExceeded">
      <!-- Test against the formatted value as the format-number command will not -->
      <!-- provide a negative zero value like '-0.000'.                           -->
      <xsl:variable name="formattedDelta" select="format-number(Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:choose>
        <xsl:when test="$formattedDelta &lt; 0">
          <xsl:variable name="absDelta" select="concat(substring('-',2 - (Delta &lt; 0)), '1') * Delta"/>
          <xsl:choose>
            <xsl:when test="$absDelta &gt; $underCutTol">
              <xsl:value-of select="'true'"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="'false'"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="'false'"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:element>

    <xsl:element name="overcutExceeded">
      <xsl:choose>
        <xsl:when test="Delta &gt; 0">
          <xsl:choose>
            <xsl:when test="Delta &gt; $overCutTol">
              <xsl:value-of select="'true'"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="'false'"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="'false'"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:element>

    <xsl:element name="stnTolExceeded">
      <xsl:variable name="absStnDelta" select="concat(substring('-',2 - (DeltaStation &lt; 0)), '1') * DeltaStation"/>
      <xsl:choose>
        <xsl:when test="$absStnDelta &gt; $stnTol">
          <xsl:value-of select="'true'"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="'false'"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:element>

  </xsl:copy>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** Create Formatted Date String ***************** -->
<!-- **************************************************************** -->
<xsl:template name="formattedDateString">
  <xsl:param name="date"/>

  <xsl:variable name="month" select="substring($date, 6, 2)"/>

  <xsl:variable name="namedMonth">
    <xsl:choose>
      <xsl:when test="$month = 1">
        <xsl:value-of select="'Jan'"/>
      </xsl:when>
      <xsl:when test="$month = 2">
        <xsl:value-of select="'Feb'"/>
      </xsl:when>
      <xsl:when test="$month = 3">
        <xsl:value-of select="'Mar'"/>
      </xsl:when>
      <xsl:when test="$month = 4">
        <xsl:value-of select="'Apr'"/>
      </xsl:when>
      <xsl:when test="$month = 5">
        <xsl:value-of select="'May'"/>
      </xsl:when>
      <xsl:when test="$month = 6">
        <xsl:value-of select="'Jun'"/>
      </xsl:when>
      <xsl:when test="$month = 7">
        <xsl:value-of select="'Jul'"/>
      </xsl:when>
      <xsl:when test="$month = 8">
        <xsl:value-of select="'Aug'"/>
      </xsl:when>
      <xsl:when test="$month = 9">
        <xsl:value-of select="'Sep'"/>
      </xsl:when>
      <xsl:when test="$month = 10">
        <xsl:value-of select="'Oct'"/>
      </xsl:when>
      <xsl:when test="$month = 11">
        <xsl:value-of select="'Nov'"/>
      </xsl:when>
      <xsl:when test="$month = 12">
        <xsl:value-of select="'Dec'"/>
      </xsl:when>
    </xsl:choose>
  </xsl:variable>

  <xsl:value-of select="concat(substring($date, 9, 2), '-', $namedMonth, '-', substring($date, 3, 2))"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************ Output Table Line ********************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputTableLine">
  <xsl:param name="Val1" select="''"/>
  <xsl:param name="Val2" select="''"/>
  <xsl:param name="Val3" select="''"/>
  <xsl:param name="hdrLine" select="'false'"/>

  <tr>
  <xsl:choose>
    <xsl:when test="$hdrLine = 'true'">
      <th width="60%" align="center" bgcolor="silver"><xsl:value-of select="$Val1"/></th>
      <th width="20%" align="center" bgcolor="silver"><xsl:value-of select="$Val2"/></th>
      <th width="20%" align="center" bgcolor="silver"><xsl:value-of select="$Val3"/></th>
    </xsl:when>
    <xsl:otherwise>
      <td width="60%" align="left"><xsl:value-of select="$Val1"/></td>
      <td width="20%" align="right"><xsl:value-of select="$Val2"/></td>
      <td width="20%" align="right"><xsl:value-of select="$Val3"/></td>
    </xsl:otherwise>
  </xsl:choose>
  </tr>

</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Output Single Element Table Line **************** -->
<!-- **************************************************************** -->
<xsl:template name="OutputSingleElementTableLine">
  <xsl:param name="Hdr" select="''"/>
  <xsl:param name="Val" select="''"/>
  <xsl:param name="HighlightVal" select="'No'"/>

  <tr>
  <th width="40%" align="left"><xsl:value-of select="$Hdr"/></th>
  <xsl:choose>
    <xsl:when test="$HighlightVal != 'No'">
      <td width="60%" align="left"><font color="red"><b><xsl:value-of select="$Val"/></b></font></td>
    </xsl:when>
    <xsl:otherwise>
      <td width="60%" align="left"><xsl:value-of select="$Val"/></td>
    </xsl:otherwise>
  </xsl:choose>
  </tr>

</xsl:template>


<!-- **************************************************************** -->
<!-- ************************* Start Table ************************** -->
<!-- **************************************************************** -->
<xsl:template name="StartTable">
  <xsl:param name="caption" select="''"/>
  <xsl:param name="includeBorders" select="'Yes'"/>
  <xsl:param name="width" select="100"/>

  <xsl:choose>
    <xsl:when test="$includeBorders = 'Yes'">
      <xsl:value-of disable-output-escaping="yes" select="'&lt;table border=1 width='"/>
      <xsl:value-of select="$width"/>
      <xsl:value-of disable-output-escaping="yes" select="'% cellpadding=2 cellspacing=0 rules=cols&gt;'"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of disable-output-escaping="yes" select="'&lt;table border=0 width='"/>
      <xsl:value-of select="$width"/>
      <xsl:value-of disable-output-escaping="yes" select="'% cellpadding=2 cellspacing=0 rules=cols&gt;'"/>
    </xsl:otherwise>
  </xsl:choose>

  <xsl:if test="$caption != ''">
    <xsl:value-of disable-output-escaping="yes" select="'&lt;caption align=&quot;left&quot;&gt;'"/>
    <xsl:value-of select="$caption"/>
    <xsl:value-of disable-output-escaping="yes" select="'&lt;/caption&gt;'"/>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************** End Table *************************** -->
<!-- **************************************************************** -->
<xsl:template name="EndTable">
  <xsl:value-of disable-output-escaping="yes" select="'&lt;/table&gt;'"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* Blank Line Output ************************ -->
<!-- **************************************************************** -->
<xsl:template name="BlankLine">
  <xsl:value-of select="' '"/>
  <BR/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Station Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatStationVal">
  <xsl:param name="stationVal"/>
  <xsl:param name="definedFmt" select="''"/>
  <xsl:param name="zoneVal" select="''"/>

  <xsl:choose>
    <xsl:when test="string(number($stationVal)) = 'NaN'">
      <xsl:value-of select="format-number($stationVal, $DecPl3, 'Standard')"/>  <!-- Return appropriate formatted null value -->
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="formatStyle">
        <xsl:choose>
          <xsl:when test="$definedFmt = ''">
            <xsl:value-of select="/JOBFile/Environment/DisplaySettings/StationingFormat"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$definedFmt"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="stnVal" select="format-number($stationVal * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:variable name="signChar">
        <xsl:choose>
          <xsl:when test="$stnVal &lt; 0.0">
            <xsl:value-of select="'-'"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="''"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="absStnVal" select="concat(substring('-',2 - ($stnVal &lt; 0)), '1') * $stnVal"/>

      <xsl:variable name="intPart" select="substring-before(format-number($absStnVal, $DecPl3, 'Standard'), '.')"/>
      <xsl:variable name="decPart" select="substring-after($stnVal, '.')"/>

      <xsl:if test="$formatStyle = '1000.0'">
        <xsl:value-of select="$stnVal"/>
      </xsl:if>

      <xsl:if test="$formatStyle = '10+00.0'">
        <xsl:choose>
          <xsl:when test="string-length($intPart) > 2">
            <xsl:value-of select="concat($signChar, substring($intPart, 1, string-length($intPart) - 2),
                                         '+', substring($intPart, string-length($intPart) - 1, 2),
                                         '.', $decPart)"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="concat($signChar, '0+', substring('00', 1, 2 - string-length($intPart)),
                                         $intPart, '.', $decPart)"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:if>

      <xsl:if test="$formatStyle = '1+000.0'">
        <xsl:choose>
          <xsl:when test="string-length($intPart) > 3">
            <xsl:value-of select="concat($signChar, substring($intPart, 1, string-length($intPart) - 3),
                                         '+', substring($intPart, string-length($intPart) - 2, 3),
                                         '.', $decPart)"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="concat($signChar, '0+', substring('000', 1, 3 - string-length($intPart)),
                                         $intPart, '.', $decPart)"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:if>

      <xsl:if test="$zoneVal != ''">
        <xsl:value-of select="':'"/>
        <xsl:value-of select="format-number($zoneVal,'0')"/>
      </xsl:if>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


</xsl:stylesheet>
