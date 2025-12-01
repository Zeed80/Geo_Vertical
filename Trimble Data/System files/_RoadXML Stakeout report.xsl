<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"   
    xmlns:msxsl="urn:schemas-microsoft-com:xslt"            
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<!-- ***************************************************************************************** -->
<!--                                Style Sheet Description                                    -->
<!-- ***************************************************************************************** -->
<!-- This style sheet is designed to work with RoadXML files only.  It creates a report of all -->
<!-- the design positions on each cross-section along the road, based on the horizontal        -->
<!-- alignment, vertical profile, superelevation and widening parameters and template          -->
<!-- definitions and assignments.  You can use this report to validate the road design prior   -->
<!-- staking out.                                                                              -->


<xsl:output method="html" omit-xml-declaration="no" encoding="utf-8"/>

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
                    NaN="                "
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
<xsl:variable name="userField1" select="'outputUnits|Distance units for report|StringMenu|3|Meters|International Feet|US Survey Feet'"/>
<xsl:variable name="outputUnits" select="'Meters'"/>
<xsl:variable name="userField2" select="'stationFormat|Format for station values|StringMenu|4|10+00.0|1+000.0|1000.0|StationIndex'"/>
<xsl:variable name="stationFormat" select="'1+000.0'"/>

<xsl:param name="stnRangeStart" select="''"/>
<xsl:param name="stnRangeEnd" select="''"/>
<xsl:param name="stnIndexIncrement" select="'20.0'"/>
<xsl:param name="coordsNE" select="'true'"/>
<xsl:param name="chainageTerminology" select="'false'"/>

<xsl:variable name="interpMethod">
  <xsl:choose>
    <xsl:when test="/TrimbleRoad/TemplatePositioning/@crosssectionInterpolationMethod">   <!-- Attribute exists so read it -->
      <xsl:value-of select="/TrimbleRoad/TemplatePositioning/@crosssectionInterpolationMethod"/>
    </xsl:when>
    <xsl:otherwise>Elevation</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="DistUnit">
  <xsl:choose>
    <xsl:when test="$outputUnits = 'International Feet'">InternationalFeet</xsl:when>
    <xsl:when test="$outputUnits = 'US Survey Feet'">USSurveyFeet</xsl:when>
    <xsl:otherwise>Metres</xsl:otherwise>
  </xsl:choose>
</xsl:variable>  
<xsl:variable name="AngleUnit"  select="'DMSDegrees'" />
<xsl:variable name="TempUnit"   select="'Celsius'" />
<xsl:variable name="PressUnit"  select="'MilliBar'" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895    </xsl:when>
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

<xsl:variable name="spiralType">
  <xsl:choose>
    <xsl:when test="/TrimbleRoad/HorizontalAlignment/@spiralType">   <!-- Attribute exists so read it -->
      <xsl:value-of select="/TrimbleRoad/HorizontalAlignment/@spiralType"/>
    </xsl:when>
    <xsl:otherwise>Clothoid</xsl:otherwise>  <!-- Default to clothoid -->
  </xsl:choose>
</xsl:variable>

<xsl:variable name="stationEquations" select="/TrimbleRoad/StationEquations"/>

<xsl:variable name="roadScaleFactor">
  <xsl:choose>
    <xsl:when test="string(number(/TrimbleRoad/RoadScaleFactor)) != 'NaN'">
      <xsl:value-of select="/TrimbleRoad/RoadScaleFactor"/>
    </xsl:when>
    <xsl:otherwise>1</xsl:otherwise>  <!-- No RoadScaleFactor defined - default to 1.0 -->
  </xsl:choose>
</xsl:variable>

<xsl:variable name="Pi" select="3.14159265358979323846264"/>
<xsl:variable name="halfPi" select="$Pi div 2.0"/>

<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>

  <title>Road Cross-sections Report</title>
  <h2>Road Cross-sections Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    html { font-family: Arial }
    body, table, td
    {
      font-size:13px;
    }
    caption
    {
      font-size:18px;
    }

    td.blackTitleLine {background-color: black; color: white; font-weight:bold}
    td.silverTitleLine {background-color:silver; font-weight:bold}
  </style>

  <link rel="stylesheet" type="text/css" href="\Program Files\General Survey\Platform.css"/>

  <head>
  </head>

  <!-- Output table with some header details -->
  <xsl:call-template name="StartTable">
    <xsl:with-param name="includeBorders" select="'No'"/>
  </xsl:call-template>
  <tr>
    <th width="25%" align="left">Alignment Name:</th>
    <th width="75%" align="left"><xsl:value-of select="/TrimbleRoad/Name"/></th>
  </tr>
  <tr>
    <th width="25%" align="left">Alignment Code:</th>
    <th width="75%" align="left"><xsl:value-of select="/TrimbleRoad/Code"/></th>
  </tr>
  <tr>
    <th width="25%" align="left">Units:</th>
    <th width="75%" align="left"><xsl:value-of select="$outputUnits"/></th>
  </tr>
  <xsl:call-template name="EndTable"/>

  <xsl:call-template name="SeparatingLine"/>
  
  <!-- Select the TrimbleRoad node to process -->
  <xsl:apply-templates select="TrimbleRoad" />

  </html>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** TrimbleRoad Node Processing ****************** -->
<!-- **************************************************************** -->
<xsl:template match="TrimbleRoad">

  <body>
    <!-- Output the horizontal alignment records - all the rest of the output comes from this -->
    <xsl:apply-templates select="HorizontalAlignment"/>

  </body>
</xsl:template>




<!-- **************************************************************** -->
<!-- **************************************************************** -->
<!-- **************************************************************** -->
<!-- ************** Horizontal Alignment Records Output ************* -->
<!-- **************************************************************** -->
<!-- **************************************************************** -->
<!-- **************************************************************** -->
<xsl:template match="HorizontalAlignment">

  <h2 align="center">Road Cross-section Points</h2>
  
  <xsl:call-template name="StartTable">
    <xsl:with-param name="includeBorders" select="'No'"/>
  </xsl:call-template>

  <xsl:call-template name="OutputTableLine">
    <xsl:with-param name="val1">Offset</xsl:with-param>
    <xsl:with-param name="val2">
      <xsl:choose>
        <xsl:when test="$coordsNE = 'true'">North</xsl:when>
        <xsl:otherwise>East</xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>
    <xsl:with-param name="val3">
      <xsl:choose>
        <xsl:when test="$coordsNE = 'true'">East</xsl:when>
        <xsl:otherwise>North</xsl:otherwise>
      </xsl:choose>
    </xsl:with-param>
    <xsl:with-param name="val4">Elevation</xsl:with-param>
    <xsl:with-param name="val5">String name</xsl:with-param>
    <xsl:with-param name="hdrLine">true</xsl:with-param>
  </xsl:call-template>

  <!-- Builds a node set of all the cross-section, hz geometry, vt geometry,  -->
  <!-- superelevation and template assignment stations.                       -->
  <xsl:variable name="roadStations">
    <xsl:call-template name="ReturnRoadStations">
      <xsl:with-param name="startStn" select="StartStation"/>
      <xsl:with-param name="endStn" select="EndStation"/>
      <xsl:with-param name="interval" select="/TrimbleRoad/StationInterval"/>
    </xsl:call-template>
  </xsl:variable>

  <!-- Provides a sorted node set of the road stations -->
  <xsl:variable name="sortedRoadStations">
    <xsl:for-each select="msxsl:node-set($roadStations)/station">
      <xsl:sort data-type="number" order="ascending" select="value"/>
      <xsl:if test="string(number(./value)) != 'NaN'">  <!-- Only include non-null stations -->
        <xsl:copy>
          <xsl:copy-of select="*"/>
        </xsl:copy>
      </xsl:if>
    </xsl:for-each>
  </xsl:variable>

  <!-- Put all the horizontal alignment elements into a node set variable so that they -->
  <!-- can be passed into the InstantaneousRadius and InstantaneousAzimuth functions.  -->
  <xsl:variable name="horizAlignment">
    <xsl:for-each select="/TrimbleRoad/HorizontalAlignment/*">
      <xsl:copy-of select="."/>
    </xsl:for-each>
  </xsl:variable>

  <!-- Put all the vertical alignment elements into a node set variable so that they -->
  <!-- can be passed into the ElevationAtStation function.                           -->
  <xsl:variable name="vertAlignment">
    <xsl:for-each select="/TrimbleRoad/VerticalAlignment/*">
      <xsl:copy-of select="."/>
    </xsl:for-each>
  </xsl:variable>

  <!-- Put all the template assignment elements into a node set variable so that they -->
  <!-- can be passed into the offset computation function.                            -->
  <xsl:variable name="templateAssignment">
    <xsl:for-each select="/TrimbleRoad/TemplatePositioning/*">
      <xsl:copy-of select="."/>
    </xsl:for-each>
  </xsl:variable>

  <!-- Put all the superelevation and widening assignment elements into a node set   -->
  <!-- variable so that they can be passed into the offset computation function.     -->
  <xsl:variable name="superWideningAssignment">
    <xsl:for-each select="/TrimbleRoad/SuperelevationAndWidening/*">
      <xsl:copy-of select="."/>
    </xsl:for-each>
  </xsl:variable>

  <!-- Put all the template definition elements into a node set variable so that they -->
  <!-- can be passed into the offset computation function.                            -->
  <xsl:variable name="templates">
    <xsl:for-each select="/TrimbleRoad/TemplateRecord">
      <xsl:element name="Template">
        <xsl:for-each select="*">
          <xsl:copy-of select="."/>
        </xsl:for-each>
      </xsl:element>
    </xsl:for-each>
  </xsl:variable>

  <!-- Now output all the cross-section details working through the stations -->
  <xsl:for-each select="msxsl:node-set($sortedRoadStations)/station">

    <xsl:if test="(string(number($stnRangeStart)) = 'NaN') or (string(number($stnRangeEnd)) = 'NaN') or
                  ((value &gt;= $stnRangeStart) and (value &lt;= $stnRangeEnd))">

      <xsl:variable name="pointCoords">
        <xsl:choose>
          <xsl:when test="north and east">
            <xsl:element name="north">
              <xsl:value-of select="north"/>
            </xsl:element>
            <xsl:element name="east">
              <xsl:value-of select="east"/>
            </xsl:element>
          </xsl:when>
          <xsl:otherwise>
            <xsl:call-template name="PositionAtStation">
              <xsl:with-param name="horizAlignment" select="$horizAlignment"/>
              <xsl:with-param name="station" select="value"/>
            </xsl:call-template>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="clElev">
        <xsl:call-template name="ElevationAtStation">
          <xsl:with-param name="theStation" select="value"/>
          <xsl:with-param name="vertAlignment" select="$vertAlignment"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="leftOffsetPosns">  <!-- Results in a node set of all the left side cross-section points -->
        <xsl:call-template name="ComputedXSOffsetsElevations">
          <xsl:with-param name="side" select="'Left'"/>
          <xsl:with-param name="station" select="value"/>
          <xsl:with-param name="centrelineElev" select="$clElev"/>
          <xsl:with-param name="templateAssignment" select="$templateAssignment"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="templates" select="$templates"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="rightOffsetPosns">  <!-- Results in a node set of all the right side cross-section points -->
        <xsl:call-template name="ComputedXSOffsetsElevations">
          <xsl:with-param name="side" select="'Right'"/>
          <xsl:with-param name="station" select="value"/>
          <xsl:with-param name="centrelineElev" select="$clElev"/>
          <xsl:with-param name="templateAssignment" select="$templateAssignment"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="templates" select="$templates"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="instAzimuth">
        <xsl:call-template name="InstantaneousAzimuth">
          <xsl:with-param name="horizAlignment" select="$horizAlignment"/>
          <xsl:with-param name="station" select="value"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="tempLeftCoords">
        <xsl:for-each select="msxsl:node-set($leftOffsetPosns)/posn[position() &gt; 1]">
          <xsl:element name="point">
            <xsl:call-template name="FollowAzimuth">
              <xsl:with-param name="azimuth">
                <xsl:call-template name="NormalisedAngle">
                  <xsl:with-param name="angle" select="$instAzimuth - 90.0"/>
                </xsl:call-template>
              </xsl:with-param>
              <xsl:with-param name="distance">
                <xsl:variable name="offset" select="offset"/>
                <xsl:value-of select="concat(substring('-',2 - ($offset &lt; 0)), '1') * $offset"/>  <!-- Absolute value -->
              </xsl:with-param>
              <xsl:with-param name="startN" select="msxsl:node-set($pointCoords)/north"/>
              <xsl:with-param name="startE" select="msxsl:node-set($pointCoords)/east"/>
              <xsl:with-param name="startElev" select="elevation"/>
            </xsl:call-template>
            <xsl:copy-of select="offset"/>
            <xsl:copy-of select="code"/>
          </xsl:element>
        </xsl:for-each>
      </xsl:variable>

      <xsl:variable name="leftCoords">
        <xsl:call-template name="ReversedNodeSet">
          <xsl:with-param name="originalNodeSet" select="$tempLeftCoords"/>
          <xsl:with-param name="count" select="count(msxsl:node-set($tempLeftCoords)/*)"/>
          <xsl:with-param name="item" select="count(msxsl:node-set($tempLeftCoords)/*)"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="rightCoords">
        <xsl:for-each select="msxsl:node-set($rightOffsetPosns)/posn[position() &gt; 1]">
          <xsl:element name="point">
            <xsl:call-template name="FollowAzimuth">
              <xsl:with-param name="azimuth">
                <xsl:call-template name="NormalisedAngle">
                  <xsl:with-param name="angle" select="$instAzimuth + 90.0"/>
                </xsl:call-template>
              </xsl:with-param>
              <xsl:with-param name="distance" select="offset"/>
              <xsl:with-param name="startN" select="msxsl:node-set($pointCoords)/north"/>
              <xsl:with-param name="startE" select="msxsl:node-set($pointCoords)/east"/>
              <xsl:with-param name="startElev" select="elevation"/>
            </xsl:call-template>
            <xsl:copy-of select="offset"/>
            <xsl:copy-of select="code"/>
          </xsl:element>
        </xsl:for-each>
      </xsl:variable>

      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="val1">
          <xsl:choose>
            <xsl:when test="$chainageTerminology = 'true'">Chainage = </xsl:when>
            <xsl:otherwise>Station = </xsl:otherwise>
          </xsl:choose>
          <xsl:variable name="equatedStation">
            <xsl:call-template name="EquatedStationValue">
              <xsl:with-param name="station" select="value"/>
              <xsl:with-param name="stationEquations" select="$stationEquations"/>
            </xsl:call-template>
          </xsl:variable>
          <xsl:call-template name="FormatStationVal">
            <xsl:with-param name="stationVal" select="msxsl:node-set($equatedStation)/stnValue"/>
            <xsl:with-param name="zoneVal" select="msxsl:node-set($equatedStation)/zone"/>
            <xsl:with-param name="definedFmt" select="$stationFormat"/>
            <xsl:with-param name="stationIndexIncrement" select="$stnIndexIncrement"/>
          </xsl:call-template>
        </xsl:with-param>
        <xsl:with-param name="stationValueLine">true</xsl:with-param>
      </xsl:call-template>

      <xsl:if test="count(msxsl:node-set($leftCoords)/point/elevation[string(number(.)) != 'NaN']) != 0">
        <!-- There are some left offset details at this station to output -->
        <xsl:for-each select="msxsl:node-set($leftCoords)/point"> <!-- Output the left side positions -->
          <xsl:if test="string(number(elevation)) != 'NaN'">  <!-- There is a valid position -->
            <xsl:call-template name="OutputTableLine">
              <xsl:with-param name="val1" select="format-number(offset * $DistConvFactor, $DecPl3, 'Standard')"/>

              <xsl:with-param name="val2">
                <xsl:choose>
                  <xsl:when test="$coordsNE = 'true'">
                    <xsl:value-of select="format-number(north * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number(east * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>

              <xsl:with-param name="val3">
                <xsl:choose>
                  <xsl:when test="$coordsNE = 'true'">
                    <xsl:value-of select="format-number(east * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number(north * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>

              <xsl:with-param name="val4" select="format-number(elevation * $DistConvFactor, $DecPl3, 'Standard')"/>

              <xsl:with-param name="val5">
                <xsl:choose>
                  <xsl:when test="(offset = 0.0) and (code = '')">CL</xsl:when>  <!-- Hardwire CL code when on centreline and no code specified -->
                  <xsl:otherwise>
                    <xsl:value-of select="code"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>
            </xsl:call-template>
          </xsl:if>
        </xsl:for-each>
      </xsl:if>

      <!-- Output the centreline point -->
      <xsl:call-template name="OutputTableLine">
        <xsl:with-param name="val1" select="format-number(0, $DecPl3, 'Standard')"/>

        <xsl:with-param name="val2">
          <xsl:choose>
            <xsl:when test="$coordsNE = 'true'">
              <xsl:value-of select="format-number(msxsl:node-set($pointCoords)/north * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="format-number(msxsl:node-set($pointCoords)/east * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:with-param>

        <xsl:with-param name="val3">
          <xsl:choose>
            <xsl:when test="$coordsNE = 'true'">
              <xsl:value-of select="format-number(msxsl:node-set($pointCoords)/east * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="format-number(msxsl:node-set($pointCoords)/north * $DistConvFactor, $DecPl3, 'Standard')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:with-param>

        <xsl:with-param name="val4" select="format-number($clElev * $DistConvFactor, $DecPl3, 'Standard')"/>

        <xsl:with-param name="val5" select="'CL'"/>  <!-- Hardwire CL code when on centreline -->
      </xsl:call-template>

      <xsl:if test="count(msxsl:node-set($rightCoords)/point/elevation[string(number(.)) != 'NaN']) != 0">
        <!-- There are some right offset details at this station to output -->
        <xsl:for-each select="msxsl:node-set($rightCoords)/point">
          <xsl:if test="string(number(elevation)) != 'NaN'">  <!-- There is a valid position -->
            <xsl:call-template name="OutputTableLine">
              <xsl:with-param name="val1" select="format-number(offset * $DistConvFactor, $DecPl3, 'Standard')"/>

              <xsl:with-param name="val2">
                <xsl:choose>
                  <xsl:when test="$coordsNE = 'true'">
                    <xsl:value-of select="format-number(north * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number(east * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>

              <xsl:with-param name="val3">
                <xsl:choose>
                  <xsl:when test="$coordsNE = 'true'">
                    <xsl:value-of select="format-number(east * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number(north * $DistConvFactor, $DecPl3, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>

              <xsl:with-param name="val4" select="format-number(elevation * $DistConvFactor, $DecPl3, 'Standard')"/>

              <xsl:with-param name="val5">
                <xsl:choose>
                  <xsl:when test="(offset = 0.0) and (code = '')">CL</xsl:when>  <!-- Hardwire CL code when on centreline and no code specified -->
                  <xsl:otherwise>
                    <xsl:value-of select="code"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:with-param>
            </xsl:call-template>
          </xsl:if>
        </xsl:for-each>
      </xsl:if>
      <xsl:call-template name="OutputTableLine"/>  <!-- Empty line after cross-section -->
    </xsl:if>
  </xsl:for-each>

  <xsl:call-template name="EndTable"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- **** Return  a Reverse Order offsetPosns Node Set Variable ***** -->
<!-- **************************************************************** -->
<xsl:template name="ReversedOffsetPosns">
  <xsl:param name="offsetPosns"/>
  <xsl:param name="count"/>
  <xsl:param name="item"/>

  <!-- This recursive function will return a node set of the passed in cross-section      -->
  <!-- positions in the reverse order (for output of left side points from left to right) -->
  <xsl:if test="$item &gt; 0">
    <xsl:choose>
      <xsl:when test="$item = $count">
        <xsl:for-each select="msxsl:node-set($offsetPosns)/posn[last()]">  <!-- Get the last element (returned first) -->
          <xsl:copy>
            <xsl:copy-of select="*"/>
          </xsl:copy>
        </xsl:for-each>
      </xsl:when>
      
      <xsl:otherwise>  <!-- Copy the appropriate preceding element -->
        <xsl:for-each select="msxsl:node-set($offsetPosns)/posn[last()]">  <!-- Get the last element -->
          <xsl:for-each select="preceding-sibling::posn[$count - $item]">  <!-- get the required preceding element -->
            <xsl:copy>
              <xsl:copy-of select="*"/>
            </xsl:copy>
          </xsl:for-each>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>

    <!-- Recurse the function decrementing the item value -->
    <xsl:call-template name="ReversedOffsetPosns">
      <xsl:with-param name="offsetPosns" select="$offsetPosns"/>
      <xsl:with-param name="count" select="$count"/>
      <xsl:with-param name="item" select="$item - 1"/>
    </xsl:call-template>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- **** Return a Node Set Variable With All Required Stations ***** -->
<!-- **************************************************************** -->
<xsl:template name="ReturnRoadStations">
  <xsl:param name="startStn"/>
  <xsl:param name="endStn"/>
  <xsl:param name="interval"/>

  <!-- Returns a node set in the following form:
       <station>
         <value>number</value>          The actual station value
         <vtType>string</vtType>        Contains a string indicating the vertical geometry type
         <hzType>string</hzType>        Contains a string indicating the horizontal geometry type
         <north>number</north>          Contains northing value for horizontal geometry points
         <east>number</east>            Contains easting value for horizontal geometry points
         <superType>string</superType>  Contains a string indicating the superelevation position type
         <widenType>string</widenType>  Contains a string indicating the widening position type
       </station>
  -->

  <xsl:choose>
    <xsl:when test="(string(number($stnRangeStart)) != 'NaN') and (string(number($stnRangeEnd)) != 'NaN') and
                    ($stnRangeStart = $stnRangeEnd)">
       <!-- This is a special case of a report on a single station - simply return a node set of the required station -->
       <xsl:element name="station">
         <xsl:element name="value">
           <xsl:value-of select="$stnRangeStart"/>
         </xsl:element>
       </xsl:element>
     </xsl:when>
     <xsl:otherwise>
       <xsl:variable name="rangeStations">
         <!-- Add the start of range station in case it is not coincident with another station -->
         <xsl:element name="station">
           <xsl:element name="value">
             <xsl:value-of select="$stnRangeStart"/>
           </xsl:element>
         </xsl:element>

         <!-- Add the end of range station in case it is not coincident with another station -->
         <xsl:element name="station">
           <xsl:element name="value">
             <xsl:value-of select="$stnRangeEnd"/>
           </xsl:element>
         </xsl:element>
       </xsl:variable>

        <!-- Create a node set variable containing all the vertical geometry stations -->
        <xsl:variable name="vertGeometryStns">
          <xsl:for-each select="/TrimbleRoad/VerticalAlignment/*">
            <xsl:choose>
              <xsl:when test="name(.) = 'VerticalPoint'">
                <xsl:element name="station">
                  <xsl:element name="value">
                    <xsl:value-of select="format-number(IntersectionPoint/Station, $DecPl5, 'Standard')"/>
                  </xsl:element>
                  <xsl:element name="vtType">
                    <xsl:choose>
                      <xsl:when test="position() = 3">VerticalStart</xsl:when>  <!-- Allow for StartStation and EndStation elements -->
                      <xsl:when test="position() = last()">VerticalEnd</xsl:when>
                      <xsl:otherwise>VPI</xsl:otherwise>
                    </xsl:choose>
                  </xsl:element>
                </xsl:element>
              </xsl:when>

              <xsl:when test="(name(.) = 'VerticalParabola') or (name(.) = 'VerticalAsymmetricParabola') or (name(.) = 'VerticalArc')">
                <xsl:choose>
                  <xsl:when test="(Length &gt; 0) or (LengthIn &gt; 0) or (LengthOut &gt; 0)">
                    <xsl:element name="station">
                      <xsl:element name="value">
                        <xsl:value-of select="format-number(StartPoint/Station, $DecPl5, 'Standard')"/>
                      </xsl:element>
                      <xsl:element name="vtType">
                        <xsl:choose>
                          <xsl:when test="name(.) = 'VerticalArc'">StartVerticalArc</xsl:when>
                          <xsl:otherwise>StartParabola</xsl:otherwise>
                        </xsl:choose>
                      </xsl:element>
                    </xsl:element>

                    <xsl:element name="station">
                      <xsl:element name="value">
                        <xsl:value-of select="format-number(EndPoint/Station, $DecPl5, 'Standard')"/>
                      </xsl:element>
                      <xsl:element name="vtType">
                        <xsl:choose>
                          <xsl:when test="name(.) = 'VerticalArc'">EndVerticalArc</xsl:when>
                          <xsl:otherwise>EndParabola</xsl:otherwise>
                        </xsl:choose>
                      </xsl:element>
                    </xsl:element>

                    <xsl:if test="string(number(SagSummitPoint/Station)) != 'NaN'"> <!-- There is a sag/summit point -->
                      <xsl:element name="station">
                        <xsl:element name="value">
                          <xsl:value-of select="format-number(SagSummitPoint/Station, $DecPl5, 'Standard')"/>
                        </xsl:element>
                        <xsl:element name="vtType">
                          <xsl:choose>
                            <xsl:when test="(SagSummitPoint/Elevation &gt; StartPoint/Elevation) and
                                            (SagSummitPoint/Elevation &gt; EndPoint/Elevation)">HighPoint</xsl:when>
                            <xsl:otherwise>LowPoint</xsl:otherwise>
                          </xsl:choose>
                        </xsl:element>
                      </xsl:element>
                    </xsl:if>
                  </xsl:when>
                  <xsl:otherwise>   <!-- Treat as a vertical point -->
                    <xsl:element name="station">
                      <xsl:element name="value">
                        <xsl:value-of select="format-number(IntersectionPoint/Station, $DecPl5, 'Standard')"/>
                      </xsl:element>
                      <xsl:element name="vtType">VPI</xsl:element>
                    </xsl:element>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:when>
            </xsl:choose>
          </xsl:for-each>
        </xsl:variable>

        <!-- Create a node set variable containing all the horizontal geometry stations -->
        <xsl:variable name="horizGeometryStns">
          <xsl:for-each select="*">
            <xsl:choose>
              <xsl:when test="name(.) = 'StartStation'">
                <xsl:element name="station">
                  <xsl:element name="value">
                    <xsl:value-of select="format-number(., $DecPl5, 'Standard')"/>
                  </xsl:element>
                  <xsl:element name="hzType">RoadStart</xsl:element>
                  <xsl:element name="north">
                    <xsl:value-of select="following-sibling::StartPoint[1]/StartCoordinate/North"/>
                  </xsl:element>
                  <xsl:element name="east">
                    <xsl:value-of select="following-sibling::StartPoint[1]/StartCoordinate/East"/>
                  </xsl:element>
                </xsl:element>
              </xsl:when>

              <xsl:when test="name(.) = 'EndStation'">
                <xsl:element name="station">
                  <xsl:element name="value">
                    <xsl:value-of select="format-number(., $DecPl5, 'Standard')"/>
                  </xsl:element>
                  <xsl:element name="hzType">RoadEnd</xsl:element>
                  <xsl:element name="north">
                    <xsl:value-of select="following-sibling::*[last()]/EndCoordinate/North"/>
                  </xsl:element>
                  <xsl:element name="east">
                    <xsl:value-of select="following-sibling::*[last()]/EndCoordinate/East"/>
                  </xsl:element>
                </xsl:element>
              </xsl:when>

              <xsl:when test="name(.) = 'StartPoint'"/> <!-- Nothing required -->

              <xsl:otherwise>
                <xsl:if test="position() != last()">  <!-- Already have the end station -->
                  <xsl:element name="station">
                    <xsl:element name="value">
                      <xsl:value-of select="format-number(EndStation, $DecPl5, 'Standard')"/>
                    </xsl:element>
                    <xsl:element name="hzType">
                      <xsl:choose>
                        <xsl:when test="(name(.) = 'Straight') and (name(following-sibling::*[1]) = 'EntrySpiral')">TangentSpiral</xsl:when>
                        <xsl:when test="(name(.) = 'Straight') and (name(following-sibling::*[1]) = 'Arc')">PointOfCurvature</xsl:when>
                        <xsl:when test="(name(.) = 'Straight') and (name(following-sibling::*[1]) = 'Straight')">IntersectionPoint</xsl:when>
                        <xsl:when test="(name(.) = 'EntrySpiral') and (name(following-sibling::*[1]) = 'Arc')">SpiralArc</xsl:when>
                        <xsl:when test="(name(.) = 'EntrySpiral') and (name(following-sibling::*[1]) = 'ExitSpiral')">SpiralSpiral</xsl:when>
                        <xsl:when test="(name(.) = 'Arc') and (name(following-sibling::*[1]) = 'Straight')">PointOfTangency</xsl:when>
                        <xsl:when test="(name(.) = 'Arc') and (name(following-sibling::*[1]) = 'Arc')">ArcArc</xsl:when>
                        <xsl:when test="(name(.) = 'Arc') and (name(following-sibling::*[1]) = 'ExitSpiral')">ArcSpiral</xsl:when>
                        <xsl:when test="(name(.) = 'Arc') and (name(following-sibling::*[1]) = 'EntrySpiral')">ArcSpiral</xsl:when>
                        <xsl:when test="(name(.) = 'ExitSpiral') and (name(following-sibling::*[1]) = 'Straight')">SpiralTangent</xsl:when>
                        <xsl:when test="(name(.) = 'ExitSpiral') and (name(following-sibling::*[1]) = 'Arc')">SpiralArc</xsl:when>
                      </xsl:choose>
                    </xsl:element>
                    <xsl:element name="north">
                      <xsl:value-of select="EndCoordinate/North"/>
                    </xsl:element>
                    <xsl:element name="east">
                      <xsl:value-of select="EndCoordinate/East"/>
                    </xsl:element>
                  </xsl:element>
                </xsl:if>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:for-each>
        </xsl:variable>

        <!-- Create a node set variable containing all the defined superelevation/widening stations -->
        <xsl:variable name="superWideningStns">
          <xsl:for-each select="/TrimbleRoad/SuperelevationAndWidening/ApplySuperelevation">
            <xsl:variable name="superType">
              <xsl:choose>
                <xsl:when test="position() = 1">SuperelevationStart</xsl:when>    <!-- Must be a superelevation start element -->
                <xsl:when test="position() = last()">SuperelevationEnd</xsl:when> <!-- Must be a superelevation end element -->
                <!-- Check for equal super values as well as the preceding or following element not having equal values -->
                <xsl:when test="(LeftSide/Superelevation * -1 = RightSide/Superelevation) and
                                ((preceding-sibling::*[1]/LeftSide/Superelevation * -1 != preceding-sibling::*[1]/RightSide/Superelevation) or
                                 (following-sibling::*[1]/LeftSide/Superelevation * -1 != following-sibling::*[1]/RightSide/Superelevation))">
                  <xsl:text>SuperelevationEqual</xsl:text>
                </xsl:when>
                <!-- Check for equal super values with the preceding and following element having equal super values that are equal or less than the current super values -->
                <xsl:when test="(LeftSide/Superelevation * -1 = RightSide/Superelevation) and
                                ((preceding-sibling::*[1]/LeftSide/Superelevation * preceding-sibling::*[1]/LeftSide/Superelevation &lt;= LeftSide/Superelevation * LeftSide/Superelevation) and
                                 (following-sibling::*[1]/LeftSide/Superelevation * following-sibling::*[1]/LeftSide/Superelevation &lt;= LeftSide/Superelevation * LeftSide/Superelevation))">
                  <xsl:text>SuperelevationMaximum</xsl:text>
                </xsl:when>
                <!-- Check for the end of a superelevation section - super values same as first element and preceding element values are different -->
                <xsl:when test="((LeftSide/Superelevation = preceding-sibling::*[last()]/LeftSide/Superelevation) and
                                 (RightSide/Superelevation = preceding-sibling::*[last()]/RightSide/Superelevation)) and
                                ((LeftSide/Superelevation != preceding-sibling::*[1]/LeftSide/Superelevation) or
                                 (RightSide/Superelevation != preceding-sibling::*[1]/RightSide/Superelevation))">
                  <xsl:text>SuperelevationEnd</xsl:text>
                </xsl:when>
                <!-- Check for the start of a superelevation section - super values same as first element and next element values are different -->
                <xsl:when test="((LeftSide/Superelevation = preceding-sibling::*[last()]/LeftSide/Superelevation) and
                                 (RightSide/Superelevation = preceding-sibling::*[last()]/RightSide/Superelevation)) and
                                ((LeftSide/Superelevation != following-sibling::*[1]/LeftSide/Superelevation) or
                                 (RightSide/Superelevation != following-sibling::*[1]/RightSide/Superelevation))">
                  <xsl:text>SuperelevationStart</xsl:text>
                </xsl:when>
                <xsl:otherwise>  <!-- Assign as superelevation interest point if not the original (first element) cross-falls -->
                  <xsl:if test="(LeftSide/Superelevation != preceding-sibling::*[last()]/LeftSide/Superelevation) and
                                 (RightSide/Superelevation != preceding-sibling::*[last()]/RightSide/Superelevation)">
                    <xsl:text>SuperelevationInterest</xsl:text>
                  </xsl:if>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:variable>

            <xsl:if test="$superType != ''">  <!-- There is a superType value so create an element -->
              <xsl:element name="station">
                <xsl:element name="value">
                  <xsl:value-of select="format-number(Station, $DecPl5, 'Standard')"/>
                </xsl:element>
                <xsl:element name="superType">
                  <xsl:value-of select="$superType"/>
                </xsl:element>
              </xsl:element>
            </xsl:if>
          </xsl:for-each>

          <xsl:for-each select="/TrimbleRoad/SuperelevationAndWidening/ApplySuperelevation">
            <xsl:variable name="widenType">
              <xsl:choose>
                <!-- Check for start of widening - the 0/0 widening record prior to a non-zero widening record -->
                <xsl:when test="((LeftSide/Widening != 0) or (RightSide/Widening != 0)) and
                                ((preceding-sibling::*[1]/LeftSide/Widening = 0) and (preceding-sibling::*[1]/RightSide/Widening = 0))">
                  <xsl:text>WideningStart</xsl:text>
                </xsl:when>
                <!-- Check for end of widening - the 0/0 widening record after to a non-zero widening record -->
                <xsl:when test="((LeftSide/Widening = 0) and (RightSide/Widening = 0)) and
                                ((preceding-sibling::*[1]/LeftSide/Widening != 0) or (preceding-sibling::*[1]/RightSide/Widening != 0))">
                  <xsl:text>WideningEnd</xsl:text>
                </xsl:when>
                <!-- Check for maximum left/right widening - the left/right widening value is greater than or equal to the preceding and next left/right widening value -->
                <xsl:when test="((LeftSide/Widening != 0) and
                                 (preceding-sibling::*[1]/LeftSide/Widening &lt;= LeftSide/Widening) and
                                 (following-sibling::*[1]/LeftSide/Widening &lt;= LeftSide/Widening)) or
                                ((RightSide/Widening != 0) and
                                 (preceding-sibling::*[1]/RightSide/Widening &lt;= RightSide/Widening) and
                                 (following-sibling::*[1]/RightSide/Widening &lt;= RightSide/Widening))">
                  <xsl:text>WideningMaximum</xsl:text>
                </xsl:when>
              </xsl:choose>
            </xsl:variable>

            <xsl:if test="$widenType != ''">  <!-- There is a widenType value so create an element -->
              <xsl:element name="station">
                <xsl:element name="value">
                  <xsl:value-of select="format-number(Station, $DecPl5, 'Standard')"/>
                </xsl:element>
                <xsl:element name="widenType">
                  <xsl:value-of select="$widenType"/>
                </xsl:element>
              </xsl:element>
            </xsl:if>
          </xsl:for-each>
        </xsl:variable>

        <!-- Create a node set variable containing all the template assignment stations -->
        <xsl:variable name="templateAssignmentStns">
          <xsl:for-each select="/TrimbleRoad/TemplatePositioning/ApplyTemplates">
            <xsl:element name="station">
              <xsl:element name="value">
                <xsl:value-of select="format-number(Station, $DecPl5, 'Standard')"/>
              </xsl:element>
            </xsl:element>
          </xsl:for-each>
        </xsl:variable>

        <!-- Create a node set variable containing all the station equation assignment stations -->
        <xsl:variable name="stationEquationStns">
          <xsl:for-each select="/TrimbleRoad/StationEquations/ApplyStationEquation">
            <xsl:element name="station">
              <xsl:element name="value">
                <xsl:value-of select="format-number(InternalStation, $DecPl5, 'Standard')"/>
              </xsl:element>
              <xsl:element name="hzType">StationEquation</xsl:element>
            </xsl:element>
          </xsl:for-each>
        </xsl:variable>

        <xsl:variable name="initStn">
          <xsl:call-template name="GetInitialStation">
            <xsl:with-param name="startStn" select="$startStn"/>
            <xsl:with-param name="interval" select="$interval"/>
          </xsl:call-template>
        </xsl:variable>

        <!-- Assemble a list of all the horizontal and vertical geometry stations dealing with any duplicates -->
        <xsl:variable name="geometryStations">
          <xsl:call-template name="CombinedHzVtSuperGeometryPts">
            <xsl:with-param name="rangeStations" select="$rangeStations"/>
            <xsl:with-param name="horizGeometryStns" select="$horizGeometryStns"/>
            <xsl:with-param name="vertGeometryStns" select="$vertGeometryStns"/>
            <xsl:with-param name="superWideningStns" select="$superWideningStns"/>
            <xsl:with-param name="templateAssignmentStns" select="$templateAssignmentStns"/>
            <xsl:with-param name="stationEquationStns" select="$stationEquationStns"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:call-template name="AddIntervalStations">
          <xsl:with-param name="startStn" select="$startStn"/>
          <xsl:with-param name="endStn" select="$endStn"/>
          <xsl:with-param name="interval" select="$interval"/>
          <xsl:with-param name="station" select="$initStn"/>
          <xsl:with-param name="geometryStations" select="$geometryStations"/>
        </xsl:call-template>

        <!-- Now add the geometry stations to the node set variable -->
        <xsl:for-each select="msxsl:node-set($geometryStations)/station">
          <xsl:copy>
            <xsl:copy-of select="*"/>
          </xsl:copy>
        </xsl:for-each>
     </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- **** Return 'rounded' interval station based on supplied stn *** -->
<!-- **************************************************************** -->
<xsl:template name="GetInitialStation">
  <xsl:param name="startStn"/>
  <xsl:param name="interval"/>

  <xsl:variable name="temp" select="$startStn mod $interval"/>
  <xsl:choose>
    <xsl:when test="$temp = 0"><xsl:value-of select="$startStn"/></xsl:when>
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$startStn &gt; 0">
          <xsl:value-of select="$startStn - $temp"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="$startStn - ($interval + $temp)"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******* Function To Return Node Set Of Hz And Vt Stations ****** -->
<!-- **************************************************************** -->
<xsl:template name="CombinedHzVtSuperGeometryPts">
  <xsl:param name="rangeStations"/>
  <xsl:param name="horizGeometryStns"/>
  <xsl:param name="vertGeometryStns"/>
  <xsl:param name="superWideningStns"/>
  <xsl:param name="templateAssignmentStns"/>
  <xsl:param name="stationEquationStns"/>

  <!-- This function returns a node set of all the combined geometry, superelevation -->
  <!-- and widening and template assignment stations combining together the details  -->
  <!-- from any duplicate stations.                                                  -->
  <xsl:variable name="combined">
    <xsl:for-each select="msxsl:node-set($rangeStations)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>

    <xsl:for-each select="msxsl:node-set($horizGeometryStns)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>

    <xsl:for-each select="msxsl:node-set($vertGeometryStns)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>

    <xsl:for-each select="msxsl:node-set($superWideningStns)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>

    <xsl:for-each select="msxsl:node-set($templateAssignmentStns)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>

    <xsl:for-each select="msxsl:node-set($stationEquationStns)/station">
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>
  </xsl:variable>
  
  <xsl:variable name="sortedCombined">
    <xsl:for-each select="msxsl:node-set($combined)/station">
      <xsl:sort data-type="number" order="ascending" select="value"/>
      <xsl:copy>
        <xsl:copy-of select="*"/>
      </xsl:copy>
    </xsl:for-each>
  </xsl:variable>
  
  <xsl:for-each select="msxsl:node-set($sortedCombined)/station">
    <xsl:variable name="currStn" select="number(value)"/>
    <xsl:variable name="nextStn" select="number(following-sibling::*[1]/value)"/>
    <xsl:variable name="prevStn" select="number(preceding-sibling::*[1]/value)"/>
    <xsl:variable name="deltaToNextStn" select="concat(substring('-',2 - (($currStn - $nextStn) &lt; 0)), '1') * ($currStn - $nextStn)"/>
    <xsl:variable name="deltaToPrevStn" select="concat(substring('-',2 - (($currStn - $prevStn) &lt; 0)), '1') * ($currStn - $prevStn)"/>
    <xsl:choose>
      <xsl:when test="number($deltaToPrevStn) &lt; 0.0005">  <!-- Output nothing in this case - will have been already dealt with -->
      </xsl:when>
      <xsl:when test="number($deltaToNextStn) &lt; 0.0005">  <!-- Essentially the same station as the next in the list -->
        <xsl:copy>
          <xsl:copy-of select="* | following-sibling::*[(concat(substring('-',2 - (($currStn - value) &lt; 0)), '1') * ($currStn - value)) &lt; 0.0001]/*[name() != 'value']"/> <!-- Assemble a union of the two elements with the same station value (without including the second value node) -->
        </xsl:copy>
      </xsl:when>
      <xsl:otherwise>
        <xsl:copy>
          <xsl:copy-of select="*"/>
        </xsl:copy>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Recursive Function To Add Interval Stations ********* -->
<!-- **************************************************************** -->
<xsl:template name="AddIntervalStations">
  <xsl:param name="startStn"/>
  <xsl:param name="endStn"/>
  <xsl:param name="interval"/>
  <xsl:param name="station"/>
  <xsl:param name="geometryStations"/>
  <xsl:param name="zone" select="1"/>

  <!-- If in valid station range add the interval station element -->
  <xsl:variable name="intervalStation">
    <xsl:choose>
      <xsl:when test="($station &gt;= $startStn) and ($station &lt;= $endStn)">
        <xsl:variable name="geomStn">
          <xsl:call-template name="IsGeometryStation">
            <xsl:with-param name="station" select="$station"/>
            <xsl:with-param name="geometryStations" select="$geometryStations"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:variable name="equatedStn">
          <xsl:call-template name="EquatedStationValue">
            <xsl:with-param name="station" select="$station"/>
            <xsl:with-param name="stationEquations" select="$stationEquations"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:element name="station">
          <xsl:choose>
            <xsl:when test="(string(number(msxsl:node-set($equatedStn)/zone)) != 'NaN') and
                            ($zone != msxsl:node-set($equatedStn)/zone)">
              <!-- We have switched to a new equated station zone - set a new station value -->
              <!-- based on the AheadStation from the current station equation.             -->
              <xsl:variable name="newInitEqStn">
                <xsl:variable name="initEquatedStn">
                  <xsl:call-template name="GetInitialStation">
                    <xsl:with-param name="startStn" select="msxsl:node-set($equatedStn)/aheadStation"/>
                    <xsl:with-param name="interval" select="$interval"/>
                  </xsl:call-template>
                </xsl:variable>
                <!-- Allow for the station equation going in a decreasing direction and add on the iterval if -->
                <!-- this is the case so that we will come 'back past' the next interval position.            -->
                <xsl:choose>
                  <xsl:when test="msxsl:node-set($equatedStn)/direction = 'Increasing'">
                    <xsl:value-of select="$initEquatedStn"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="$initEquatedStn + $interval"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:variable>
              <!-- The first zone change encountered will be the equated station but this will be -->
              <!-- skipped because it is a geometry station.  Get the true station of the next    -->
              <!-- interval position and then move back to the previous one so the next recursion -->
              <!-- will bring us to the correct interval station.                                 -->
              <!-- Get the true station value for the next interval station -->
              <xsl:variable name="nextTrueStn">
                <xsl:call-template name="TrueStationValue">
                  <xsl:with-param name="equatedStation">
                    <xsl:choose>
                      <xsl:when test="msxsl:node-set($equatedStn)/direction = 'Increasing'">
                        <xsl:value-of select="$newInitEqStn + $interval"/>
                      </xsl:when>
                      <xsl:otherwise>
                        <xsl:value-of select="$newInitEqStn - $interval"/>
                      </xsl:otherwise>
                    </xsl:choose>
                  </xsl:with-param>
                  <xsl:with-param name="zone" select="msxsl:node-set($equatedStn)/zone"/>
                  <xsl:with-param name="stationEquations" select="$stationEquations"/>
                </xsl:call-template>
              </xsl:variable>
              <xsl:value-of select="$nextTrueStn - $interval"/>
            </xsl:when>
            <xsl:otherwise>  <!-- Same zone so simply set the station element to the passed in $station -->
              <xsl:value-of select="$station"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>

        <xsl:element name="zone">
          <xsl:value-of select="msxsl:node-set($equatedStn)/zone"/>
        </xsl:element>

        <xsl:if test="$geomStn = 'No'">  <!-- Only add interval station if it is not a geometry station -->
          <xsl:element name="add">true</xsl:element>
        </xsl:if>
      </xsl:when>

      <xsl:otherwise>
        <xsl:element name="station">
          <xsl:value-of select="$station"/>
        </xsl:element>
        <xsl:element name="zone">
          <xsl:value-of select="$zone"/>
        </xsl:element>
        <xsl:element name="add">false</xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:if test="msxsl:node-set($intervalStation)/add = 'true'">
    <xsl:element name="station">
      <xsl:element name="value">
        <xsl:value-of select="msxsl:node-set($intervalStation)/station"/>
      </xsl:element>
      <xsl:element name="hzType">Interval</xsl:element>
    </xsl:element>
  </xsl:if>

  <xsl:if test="$station &lt; $endStn">
    <xsl:call-template name="AddIntervalStations">
      <xsl:with-param name="startStn" select="$startStn"/>
      <xsl:with-param name="endStn" select="$endStn"/>
      <xsl:with-param name="interval" select="$interval"/>
      <xsl:with-param name="station" select="msxsl:node-set($intervalStation)/station + $interval"/>
      <xsl:with-param name="geometryStations" select="$geometryStations"/>
      <xsl:with-param name="zone" select="msxsl:node-set($intervalStation)/zone"/>
    </xsl:call-template>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Function To Check If Geometry Station Value ******** -->
<!-- **************************************************************** -->
<xsl:template name="IsGeometryStation">
  <xsl:param name="station"/>
  <xsl:param name="geometryStations"/>

  <xsl:variable name="test">
    <xsl:for-each select="msxsl:node-set($geometryStations)/station">
      <xsl:variable name="absDeltaStn" select="concat(substring('-',2 - (($station - value) &lt; 0)), '1') * ($station - value)"/>
      <xsl:if test="$absDeltaStn &lt; 0.0005">x</xsl:if>  <!-- Effectively the same station value -->
    </xsl:for-each>
  </xsl:variable>
  
  <xsl:choose>
    <xsl:when test="string-length($test) &gt; 0">Yes</xsl:when>
    <xsl:otherwise>No</xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return Computed Cross-section Positions ************ -->
<!-- **************************************************************** -->
<xsl:template name="ComputedXSOffsetsElevations">
  <xsl:param name="side" select="'Left'"/>
  <xsl:param name="station"/>
  <xsl:param name="centrelineElev"/>
  <xsl:param name="templateAssignment"/>
  <xsl:param name="superWideningAssignment"/>
  <xsl:param name="templates"/>

  <!-- This function returns a node set of the computed cross-section points for -->
  <!-- the specified station and side.  Effectively applies the appropriate      -->
  <!-- cross-section template for the station or interpolates the points based   -->
  <!-- on the preceding and next templates.                                      -->
  <!-- This function returns a node set posn elements in the following form
          <posn>
            <elevation>number</elevation>
            <offset>number</offset>
            <code>string</code>
          </posn>
  -->
  
  <xsl:variable name="templateNames">
    <xsl:call-template name="GetTemplateNames">
      <xsl:with-param name="station" select="$station"/>
      <xsl:with-param name="templateAssignment" select="$templateAssignment"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="sign">
    <xsl:choose>
      <xsl:when test="$side = 'Left'">-1.0</xsl:when>
      <xsl:otherwise>1.0</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Determine the appropriate previous and next template names and stations -->
  <xsl:variable name="prevTemplateName">
    <xsl:choose>
      <xsl:when test="$side = 'Left'"><xsl:value-of select="msxsl:node-set($templateNames)/prevLeftTemplateName"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="msxsl:node-set($templateNames)/prevRightTemplateName"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="prevTemplateStation">
    <xsl:choose>
      <xsl:when test="$side = 'Left'"><xsl:value-of select="format-number(msxsl:node-set($templateNames)/prevLeftTemplateStation, $DecPl5, 'Standard')"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="format-number(msxsl:node-set($templateNames)/prevRightTemplateStation, $DecPl5, 'Standard')"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="nextTemplateName">
    <xsl:choose>
      <xsl:when test="$side = 'Left'"><xsl:value-of select="msxsl:node-set($templateNames)/nextLeftTemplateName"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="msxsl:node-set($templateNames)/nextRightTemplateName"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="nextTemplateStation">
    <xsl:choose>
      <xsl:when test="$side = 'Left'"><xsl:value-of select="format-number(msxsl:node-set($templateNames)/nextLeftTemplateStation, $DecPl5, 'Standard')"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="format-number(msxsl:node-set($templateNames)/nextRightTemplateStation, $DecPl5, 'Standard')"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <!-- If we have a template defined for this specific station (with the same -->
    <!-- template name before and after), we have no next template defined or   -->
    <!-- we have a next template defined and its station is the same as our     -->
    <!-- current station.                                                       -->
    <xsl:when test="(($prevTemplateName = $nextTemplateName) and ($prevTemplateName != '')) or
                    (($prevTemplateName != '') and ($nextTemplateName = '')) or
                    (($nextTemplateName != '') and ((concat(substring('-',2 - (($station - $nextTemplateStation) &lt; 0)), '1') * ($station - $nextTemplateStation)) &lt; 0.0001))">
      <xsl:variable name="templateName">
        <xsl:choose>   <!-- Use the next template if appropriate (no prev template name or we are right at the station of the next template) otherwise use the previous template -->
          <xsl:when test="($prevTemplateName = '') or
                          (($nextTemplateName != '') and ((concat(substring('-',2 - (($station - $nextTemplateStation) &lt; 0)), '1') * ($station - $nextTemplateStation)) &lt; 0.0001))">
            <xsl:value-of select="$nextTemplateName"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$prevTemplateName"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="deltas">
        <xsl:call-template name="GetTemplateDeltas">  <!-- This function computes the deltas for the specified template -->
          <xsl:with-param name="templates" select="$templates"/>
          <xsl:with-param name="templateNames" select="$templateNames"/>
          <xsl:with-param name="templateName" select="$templateName"/>
          <xsl:with-param name="station" select="$station"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="side" select="$side"/>
          <xsl:with-param name="prev" select="'true'"/>
        </xsl:call-template>
      </xsl:variable>
        
      <xsl:variable name="clElev" select="$centrelineElev + msxsl:node-set($deltas)/xsPos[1]/clElevAdj[1]/value"/>
      
      <xsl:element name="posn">
        <!-- Add the centreline position first -->
        <xsl:element name="elevation">
          <xsl:value-of select="$clElev"/>
        </xsl:element>

        <xsl:element name="offset">
          <xsl:value-of select="0"/>
        </xsl:element>

        <xsl:element name="code">
          <xsl:value-of select="''"/>
        </xsl:element>
      </xsl:element>

      <!-- Now add the delta elevation and delta offset to each cross-section point plus the code -->
      <xsl:for-each select="msxsl:node-set($deltas)/xsPos">
        <xsl:variable name="currPos" select="position()"/>
        <xsl:element name="posn">
          <xsl:element name="elevation">
            <xsl:value-of select="$clElev + sum(msxsl:node-set($deltas)/xsPos[position() &lt;= $currPos]/deltaElev)"/>
          </xsl:element>

          <xsl:element name="offset">
            <xsl:value-of select="sum(msxsl:node-set($deltas)/xsPos[position() &lt;= $currPos]/deltaOffset) * $sign"/>
          </xsl:element>

          <xsl:element name="code">
            <xsl:value-of select="msxsl:node-set($deltas)/xsPos[position() = $currPos]/code"/>
          </xsl:element>
        </xsl:element>
      </xsl:for-each>
    </xsl:when>
    
    <!-- Interpolate the values if both templates are available but have different names -->
    <xsl:when test="($prevTemplateName != '') and ($nextTemplateName != '')">
      <xsl:variable name="initPrevDeltas">
        <xsl:call-template name="GetTemplateDeltas">  <!-- This function computes the deltas for the specified template (previous) -->
          <xsl:with-param name="templates" select="$templates"/>
          <xsl:with-param name="templateNames" select="$templateNames"/>
          <xsl:with-param name="templateName" select="$prevTemplateName"/>
          <xsl:with-param name="station" select="$station"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="side" select="$side"/>
          <xsl:with-param name="prev" select="'true'"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="initNextDeltas">
        <xsl:call-template name="GetTemplateDeltas">  <!-- This function computes the deltas for the specified template (next) -->
          <xsl:with-param name="templates" select="$templates"/>
          <xsl:with-param name="templateNames" select="$templateNames"/>
          <xsl:with-param name="templateName" select="$nextTemplateName"/>
          <xsl:with-param name="station" select="$station"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="side" select="$side"/>
          <xsl:with-param name="prev" select="'false'"/>
        </xsl:call-template>
      </xsl:variable>

      <!-- Check if the prev and next templates have the same number of elements and if not add enough -->
      <!-- zero delta elements to the end of the the template with less elements.                      -->
      <xsl:variable name="prevDeltas">
        <xsl:choose>
          <xsl:when test="count(msxsl:node-set($initPrevDeltas)/xsPos) &lt; count(msxsl:node-set($initNextDeltas)/xsPos)">
            <xsl:for-each select="msxsl:node-set($initPrevDeltas)/xsPos">
              <xsl:copy-of select="."/>
            </xsl:for-each>
            <xsl:for-each select="msxsl:node-set($initNextDeltas)/xsPos">
              <xsl:if test="position() &gt; count(msxsl:node-set($initPrevDeltas)/xsPos)">
                <xsl:element name="xsPos">
                  <xsl:element name="deltaElev">0</xsl:element>
                  <xsl:element name="deltaOffset">0</xsl:element>
                  <xsl:element name="code"></xsl:element>
                  <xsl:copy-of select="msxsl:node-set($initPrevDeltas)/xsPos[1]/clElevAdj"/>
                </xsl:element>
              </xsl:if>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise>
            <xsl:copy-of select="$initPrevDeltas"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="nextDeltas">
        <xsl:choose>
          <xsl:when test="count(msxsl:node-set($initNextDeltas)/xsPos) &lt; count(msxsl:node-set($initPrevDeltas)/xsPos)">
            <xsl:for-each select="msxsl:node-set($initNextDeltas)/xsPos">
              <xsl:copy-of select="."/>
            </xsl:for-each>
            <xsl:for-each select="msxsl:node-set($initPrevDeltas)/xsPos">
              <xsl:if test="position() &gt; count(msxsl:node-set($initNextDeltas)/xsPos)">
                <xsl:element name="xsPos">
                  <xsl:element name="deltaElev">0</xsl:element>
                  <xsl:element name="deltaOffset">0</xsl:element>
                  <xsl:element name="code"></xsl:element>
                  <xsl:copy-of select="msxsl:node-set($initNextDeltas)/xsPos[1]/clElevAdj"/>
                </xsl:element>
              </xsl:if>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise>
            <xsl:copy-of select="$initNextDeltas"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="prevCLElevAdj">
        <xsl:choose>
          <xsl:when test="string(number(msxsl:node-set($prevDeltas)/xsPos[1]/clElevAdj[1]/value)) != 'NaN'">
            <xsl:value-of select="msxsl:node-set($prevDeltas)/xsPos[1]/clElevAdj[1]/value"/>
          </xsl:when>
          <xsl:otherwise>0</xsl:otherwise>
        </xsl:choose>
      </xsl:variable> 

      <xsl:variable name="nextCLElevAdj">
        <xsl:choose>
          <xsl:when test="string(number(msxsl:node-set($nextDeltas)/xsPos[1]/clElevAdj[1]/value)) != 'NaN'">
            <xsl:value-of select="msxsl:node-set($nextDeltas)/xsPos[1]/clElevAdj[1]/value"/>
          </xsl:when>
          <xsl:otherwise>0</xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="clElevAdj">
        <xsl:variable name="prevPivotSideTemplateStation" select="msxsl:node-set($nextDeltas)/xsPos[1]/clElevAdj[1]/prevStn"/>
        <xsl:variable name="nextPivotSideTemplateStation" select="msxsl:node-set($nextDeltas)/xsPos[1]/clElevAdj[1]/nextStn"/>
        <xsl:choose>
          <xsl:when test="($prevPivotSideTemplateStation = $nextPivotSideTemplateStation) or
                          ($prevCLElevAdj = $nextCLElevAdj)">
            <xsl:value-of select="$prevCLElevAdj"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$prevCLElevAdj + ($nextCLElevAdj - $prevCLElevAdj) * ($station - $prevPivotSideTemplateStation) div ($nextPivotSideTemplateStation - $prevPivotSideTemplateStation)"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable> 

      <xsl:variable name="clElev" select="$centrelineElev + $clElevAdj"/>

      <xsl:element name="posn">
        <!-- Add the centreline position first -->
        <xsl:element name="elevation">
          <xsl:value-of select="$clElev"/>
        </xsl:element>

        <xsl:element name="offset">
          <xsl:value-of select="0"/>
        </xsl:element>

        <xsl:element name="code">
          <xsl:value-of select="''"/>
        </xsl:element>
      </xsl:element>

      <!-- Now add the delta elevation and delta offset to each cross-section point plus the code -->
      <xsl:for-each select="msxsl:node-set($prevDeltas)/xsPos">
        <xsl:variable name="currPos" select="position()"/>
        <xsl:variable name="prevDeltaElev" select="sum(msxsl:node-set($prevDeltas)/xsPos[position() &lt;= $currPos]/deltaElev)"/>
        <xsl:variable name="nextDeltaElev" select="sum(msxsl:node-set($nextDeltas)/xsPos[position() &lt;= $currPos]/deltaElev)"/>

        <xsl:variable name="prevOffset" select="sum(msxsl:node-set($prevDeltas)/xsPos[position() &lt;= $currPos]/deltaOffset)"/>
        <xsl:variable name="nextOffset" select="sum(msxsl:node-set($nextDeltas)/xsPos[position() &lt;= $currPos]/deltaOffset)"/>

        <xsl:variable name="prevCode">
          <xsl:value-of select="msxsl:node-set($prevDeltas)/xsPos[position() = $currPos]/code"/>
        </xsl:variable>

        <xsl:variable name="nextCode">
          <xsl:value-of select="msxsl:node-set($nextDeltas)/xsPos[position() = $currPos]/code"/>
        </xsl:variable>

        <!-- If we have valid values from both the previous and next templates assign the interpolated values to the returned element -->
        <xsl:if test="(string(number($prevDeltaElev)) != 'NaN') and (string(number($nextDeltaElev)) != 'NaN') and
                      (string(number($prevOffset)) != 'NaN') and (string(number($nextOffset)) != 'NaN')">
          <xsl:element name="posn">
            <xsl:element name="elevation">
              <xsl:choose>
                <xsl:when test="$interpMethod = 'Elevation'">
                  <xsl:value-of select="$clElev + $prevDeltaElev + ($nextDeltaElev - $prevDeltaElev) * ($station - $prevTemplateStation) div ($nextTemplateStation - $prevTemplateStation)"/>
                </xsl:when>
                <xsl:otherwise>  <!-- Must be cross-slope interpolation -->
                  <xsl:variable name="deltaElev">
                    <xsl:call-template name="InterpolatedDeltaElevByGrade">
                      <xsl:with-param name="prevXSDeltas" select="$prevDeltas"/>
                      <xsl:with-param name="nextXSDeltas" select="$nextDeltas"/>
                      <xsl:with-param name="station" select="$station"/>
                      <xsl:with-param name="prevTemplateStation" select="$prevTemplateStation"/>
                      <xsl:with-param name="nextTemplateStation" select="$nextTemplateStation"/>
                      <xsl:with-param name="currPos" select="$currPos"/>
                    </xsl:call-template>
                  </xsl:variable>
                  <xsl:value-of select="$clElev + $deltaElev"/>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:element>

            <xsl:element name="offset">
              <xsl:value-of select="($prevOffset + ($nextOffset - $prevOffset) * ($station - $prevTemplateStation) div ($nextTemplateStation - $prevTemplateStation)) * $sign"/>
            </xsl:element>

            <xsl:element name="code">
              <xsl:choose>
                <xsl:when test="($prevCode = '') and ($nextCode != '')">  <!-- No previous code but there is a next code so return $nextCode -->
                  <xsl:value-of select="$prevCode"/>
                </xsl:when>
                <xsl:when test="($prevCode != '') and ($nextCode = '')">  <!-- No next code but there is a previous code so return $prevCode -->
                  <xsl:value-of select="$prevCode"/>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:value-of select="$prevCode"/>  <!-- There are both previous and next codes - return $prevCode -->
                </xsl:otherwise>          
              </xsl:choose>
            </xsl:element>
          </xsl:element>
        </xsl:if>

      </xsl:for-each>
    </xsl:when>
    
    <!-- Can't get the cross-section details - return null elevation and offset values and 0 for centreline elevation adjustment -->
    <xsl:otherwise>
      <xsl:element name="posn">
        <xsl:element name="elevation"/>

        <xsl:element name="offset"/>

        <xsl:element name="clElevAdj">0</xsl:element>
      </xsl:element>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Layout Functions ************************ -->
<!-- **************************************************************** -->

<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************* Start Table ************************** -->
<!-- **************************************************************** -->
<xsl:template name="StartTable">
  <xsl:param name="includeBorders" select="'Yes'"/>
  <xsl:choose>
    <xsl:when test="$includeBorders = 'Yes'">
      <xsl:value-of disable-output-escaping="yes" select="'&lt;table border=&quot;1&quot; width=&quot;100%&quot; cellpadding=&quot;2&quot; cellspacing=&quot;0&quot; rules=&quot;cols&quot;&gt;'"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of disable-output-escaping="yes" select="'&lt;table border=&quot;0&quot; width=&quot;100%&quot; cellpadding=&quot;2&quot; cellspacing=&quot;0&quot; rules=&quot;none&quot;&gt;'"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************** End Table *************************** -->
<!-- **************************************************************** -->
<xsl:template name="EndTable">
  <xsl:value-of disable-output-escaping="yes" select="'&lt;/table&gt;'"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************************ Output Table Line ********************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputTableLine">
  <xsl:param name="val1" select="''"/>
  <xsl:param name="val2" select="''"/>
  <xsl:param name="val3" select="''"/>
  <xsl:param name="val4" select="''"/>
  <xsl:param name="val5" select="''"/>
  <xsl:param name="hdrLine" select="'false'"/>
  <xsl:param name="stationValueLine" select="'false'"/>

  <xsl:variable name="hdrStyle">
    <xsl:if test="$hdrLine = 'true'">blackTitleLine</xsl:if>
  </xsl:variable>

  <tr>
  <xsl:choose>
    <xsl:when test="$stationValueLine = 'true'">
      <td colspan="8" align="left" class="silverTitleLine"><xsl:value-of select="$val1"/></td>
    </xsl:when>

    <xsl:otherwise>
      <td width="21%" align="right" class="{$hdrStyle}"><xsl:value-of select="$val1"/></td>
      <td width="21%" align="right" class="{$hdrStyle}"><xsl:value-of select="$val2"/></td>
      <td width="21%" align="right" class="{$hdrStyle}"><xsl:value-of select="$val3"/></td>
      <td width="18%" align="right" class="{$hdrStyle}"><xsl:value-of select="$val4"/></td>
      <td width="3%"  align="right" class="{$hdrStyle}">&#160;</td>
      <td width="18%" align="left"  class="{$hdrStyle}"><xsl:value-of select="$val5"/></td>
    </xsl:otherwise>
  </xsl:choose>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******* Return equated station value for a given station ******* -->
<!-- **************************************************************** -->
<xsl:template name="EquatedStationValue">
  <xsl:param name="station"/>
  <xsl:param name="stationEquations"/>

  <!-- Returns a node-set variable with the elements:                                                  -->
  <!--   stnValue - the equated station value                                                          -->
  <!--   zone - the equated station zone                                                               -->
  <!--   aheadStation - the ahead station for the zone (only present when equated station found)       -->
  <!--   direction - the direction (Increasing or Decreasing, only present when equated station found) -->

  <xsl:choose>
    <xsl:when test="count(msxsl:node-set($stationEquations)/ApplyStationEquation) = 0">
      <!-- No station equations defined - just return the passed in station -->
      <xsl:element name="stnValue" namespace="">
        <xsl:value-of select="$station"/>
      </xsl:element>
      <xsl:element name="zone" namespace=""></xsl:element>
    </xsl:when>

    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$station &lt; msxsl:node-set($stationEquations)/ApplyStationEquation[1]/BackStation">
          <!-- Passed in station is before the first station equation (zone 1) -->
          <xsl:element name="stnValue" namespace="">
            <xsl:value-of select="$station"/>
          </xsl:element>
          <xsl:element name="zone" namespace="">1</xsl:element>
          <xsl:element name="direction" namespace="">Increasing</xsl:element>
        </xsl:when>

        <xsl:otherwise>  <!-- Must be a station beyond the first station equation zone -->
          <xsl:variable name="equatedStns">
            <xsl:for-each select="msxsl:node-set($stationEquations)/ApplyStationEquation">
              <xsl:choose>
                <xsl:when test="($station &lt; following-sibling::*[1]/InternalStation) or (position() = last())">
                  <xsl:variable name="deltaStn" select="$station - InternalStation"/>
                  <xsl:element name="item" namespace="">
                    <xsl:element name="stnValue" namespace="">
                      <xsl:choose>
                        <xsl:when test="Direction = 'Increasing'">
                          <xsl:value-of select="AheadStation + $deltaStn"/>
                        </xsl:when>
                        <xsl:otherwise>
                          <xsl:value-of select="AheadStation - $deltaStn"/>
                        </xsl:otherwise>
                      </xsl:choose>
                    </xsl:element>
                    <xsl:element name="zone" namespace="">
                      <xsl:value-of select="position() + 1"/>
                    </xsl:element>
                    <xsl:element name="aheadStation" namespace="">
                      <xsl:value-of select="AheadStation"/>
                    </xsl:element>
                    <xsl:element name="direction" namespace="">
                      <xsl:value-of select="Direction"/>
                    </xsl:element>
                  </xsl:element>
                </xsl:when>
              </xsl:choose>
            </xsl:for-each>
          </xsl:variable>

          <xsl:element name="stnValue" namespace="">
            <xsl:value-of select="msxsl:node-set($equatedStns)/item[1]/stnValue"/>
          </xsl:element>
          <xsl:element name="zone" namespace="">
            <xsl:value-of select="msxsl:node-set($equatedStns)/item[1]/zone"/>
          </xsl:element>
          <xsl:element name="aheadStation" namespace="">
            <xsl:value-of select="msxsl:node-set($equatedStns)/item[1]/aheadStation"/>
          </xsl:element>
          <xsl:element name="direction" namespace="">
            <xsl:value-of select="msxsl:node-set($equatedStns)/item[1]/direction"/>
          </xsl:element>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *** Return true station for a given equated station and zone *** -->
<!-- **************************************************************** -->
<xsl:template name="TrueStationValue">
  <xsl:param name="equatedStation"/>
  <xsl:param name="zone"/>
  <xsl:param name="stationEquations"/>

  <xsl:choose>
    <xsl:when test="count(msxsl:node-set($stationEquations)/ApplyStationEquation) = 0">
      <!-- No station equations defined - just return the passed in equated station -->
      <xsl:value-of select="$equatedStation"/>
    </xsl:when>

    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$zone = 1">  <!-- Equated station is in the first zone - return the passed in equated station -->
          <xsl:if test="$equatedStation &lt; msxsl:node-set($stationEquations)/ApplyStationEquation[1]/BackStation">
            <!-- The passed in equatedStation is before the first specified BackStation -->
            <xsl:value-of select="$equatedStation"/>
          </xsl:if>
        </xsl:when>

        <xsl:otherwise>
          <xsl:for-each select="msxsl:node-set($stationEquations)/ApplyStationEquation[number($zone - 1)]">
            <xsl:if test="((Direction = 'Increasing') and ($equatedStation &gt;= AheadStation)) or
                          ((Direction = 'Decreasing') and ($equatedStation &lt;= AheadStation))">
              <!-- The passed in equatedStation is in the correct relationship to the AheadStation -->
              <!-- Now check that if this is not the last zone the equatedStation is before the start of the next one -->
              <xsl:variable name="validValue">
                <xsl:choose>
                  <xsl:when test="$zone &lt; count(msxsl:node-set($stationEquations)/ApplyStationEquation) + 1">
                    <xsl:if test="((Direction = 'Increasing') and ($equatedStation &lt;= following-sibling::*[1]/BackStation)) or
                                  ((Direction = 'Decreasing') and ($equatedStation &gt;= following-sibling::*[1]/BackStation))">
                      <xsl:value-of select="'true'"/>
                    </xsl:if>
                  </xsl:when>
                  <xsl:otherwise>true</xsl:otherwise>
                </xsl:choose>
              </xsl:variable>
              <xsl:if test="$validValue = 'true'">
                <xsl:variable name="deltaStn" select="concat(substring('-',2 - (($equatedStation - AheadStation) &lt; 0)), '1') * ($equatedStation - AheadStation)"/>
                <xsl:value-of select="InternalStation + $deltaStn"/>
              </xsl:if>
            </xsl:if>
          </xsl:for-each>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Follow Azimuth to Compute New Point Coords *********** -->
<!-- **************************************************************** -->
<xsl:template name="FollowAzimuth">
  <xsl:param name="azimuth"/>  <!-- in degrees -->
  <xsl:param name="distance"/>
  <xsl:param name="startN"/>
  <xsl:param name="startE"/>
  <xsl:param name="startElev" select="''"/>
  <xsl:param name="endElev" select="''"/>
  <xsl:param name="elevInterpLength" select="''"/>
  <xsl:param name="grade"/>

  <xsl:variable name="sineVal">
    <xsl:call-template name="Sine">
      <xsl:with-param name="theAngle" select="$azimuth * $Pi div 180.0"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="cosineVal">
    <xsl:call-template name="Cosine">
      <xsl:with-param name="theAngle" select="$azimuth * $Pi div 180.0"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="newElev">
    <xsl:choose>
      <xsl:when test="(string(number($startElev)) != 'NaN') and (string(number($endElev)) != 'NaN')">
        <xsl:value-of select="($startElev + $endElev) div 2.0"/> <!-- Return average elevation -->
      </xsl:when>
      <xsl:when test="(string(number($startElev)) != 'NaN') and (string(number($grade)) != 'NaN') and
                      (string(number($elevInterpLength)) != 'NaN')">
        <xsl:value-of select="$startElev + $elevInterpLength * $grade"/> <!-- Apply the grade over the interpolation length to the startElev -->
      </xsl:when>
      <xsl:otherwise><xsl:value-of select="$startElev"/></xsl:otherwise> <!-- Return startElev elevation -->
    </xsl:choose>
  </xsl:variable>

  <!-- Return the coords as a node-set variable -->
  <xsl:element name="north" namespace="">
    <xsl:value-of select="$startN + $cosineVal * $distance"/>
  </xsl:element>
  <xsl:element name="east" namespace="">
    <xsl:value-of select="$startE + $sineVal * $distance"/>
  </xsl:element>
  <xsl:element name="elevation" namespace="">
    <xsl:value-of select="$newElev"/>
  </xsl:element>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Return Angle between 0 and 360 or -180 to 180 degrees **** -->
<!-- **************************************************************** -->
<xsl:template name="NormalisedAngle">
  <xsl:param name="angle"/>
  <xsl:param name="plusMinus180" select="'false'"/>

  <xsl:variable name="fullCircleAngle">
    <xsl:choose>
      <xsl:when test="$angle &lt; 0">
        <xsl:variable name="newAngle">
          <xsl:value-of select="$angle + 360.0"/>
        </xsl:variable>
        <xsl:call-template name="NormalisedAngle">
          <xsl:with-param name="angle" select="$newAngle"/>
        </xsl:call-template>
      </xsl:when>

      <xsl:when test="$angle &gt;= 360.0">
        <xsl:variable name="newAngle">
          <xsl:value-of select="$angle - 360.0"/>
        </xsl:variable>
        <xsl:call-template name="NormalisedAngle">
          <xsl:with-param name="angle" select="$newAngle"/>
        </xsl:call-template>
      </xsl:when>

      <xsl:otherwise>
        <xsl:value-of select="$angle"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$plusMinus180 = 'false'">
      <xsl:value-of select="$fullCircleAngle"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$fullCircleAngle &lt;= 180.0">
          <xsl:value-of select="$fullCircleAngle"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="$fullCircleAngle - 360.0"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Station Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatStationVal">
  <xsl:param name="stationVal"/>
  <xsl:param name="zoneVal" select="''"/>
  <xsl:param name="definedFmt" select="''"/>
  <xsl:param name="stationIndexIncrement" select="''"/>
  <xsl:param name="decPlDefnStr" select="''"/>
  <xsl:param name="includeUnitsAbbrev" select="'false'"/>
  <xsl:param name="distUnitAbbrev" select="''"/>

  <xsl:variable name="decPl">
    <xsl:choose>
      <xsl:when test="$decPlDefnStr != ''">
        <xsl:value-of select="$decPlDefnStr"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$DecPl3"/>  <!-- Default to 3 decimal places -->
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="string(number($stationVal)) = 'NaN'">
      <xsl:value-of select="format-number($stationVal, $decPl, 'Standard')"/>  <!-- Return appropriate formatted null value -->
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

      <xsl:variable name="stnIndexIncrement">
        <xsl:choose>
          <xsl:when test="string(number($stationIndexIncrement)) = 'NaN'">
            <xsl:value-of select="/JOBFile/Environment/DisplaySettings/StationIndexIncrement"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$stationIndexIncrement"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="stnVal" select="format-number($stationVal * $DistConvFactor, $decPl, 'Standard')"/>
      <xsl:variable name="signChar">
        <xsl:if test="$stnVal &lt; 0.0">-</xsl:if>
      </xsl:variable>

      <xsl:variable name="absStnVal" select="concat(substring('-',2 - ($stnVal &lt; 0)), '1') * $stnVal"/>

      <xsl:variable name="intPart" select="substring-before(format-number($absStnVal, $DecPl3, 'Standard'), '.')"/>
      <xsl:variable name="decPart" select="substring-after($stnVal, '.')"/>

      <xsl:if test="$formatStyle = '1000.0'">
        <xsl:value-of select="$stnVal"/>
      </xsl:if>

      <xsl:if test="$formatStyle = '10+00.0'">
        <xsl:choose>
          <xsl:when test="string-length($intPart) &gt; 2">
            <xsl:value-of select="concat($signChar, substring($intPart, 1, string-length($intPart) - 2),
                                         '+', substring($intPart, string-length($intPart) - 1, 2))"/>
            <xsl:if test="$decPart != ''">
              <xsl:text>.</xsl:text>
              <xsl:value-of select="$decPart"/>
            </xsl:if>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="concat($signChar, '0+', substring('00', 1, 2 - string-length($intPart)), $intPart)"/>
            <xsl:if test="$decPart != ''">
              <xsl:text>.</xsl:text>
              <xsl:value-of select="$decPart"/>
            </xsl:if>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:if>

      <xsl:if test="$formatStyle = '1+000.0'">
        <xsl:choose>
          <xsl:when test="string-length($intPart) &gt; 3">
            <xsl:value-of select="concat($signChar, substring($intPart, 1, string-length($intPart) - 3),
                                         '+', substring($intPart, string-length($intPart) - 2, 3))"/>
            <xsl:if test="$decPart != ''">
              <xsl:text>.</xsl:text>
              <xsl:value-of select="$decPart"/>
            </xsl:if>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="concat($signChar, '0+', substring('000', 1, 3 - string-length($intPart)), $intPart)"/>
            <xsl:if test="$decPart != ''">
              <xsl:text>.</xsl:text>
              <xsl:value-of select="$decPart"/>
            </xsl:if>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:if>

      <xsl:if test="$formatStyle = 'StationIndex'">
        <xsl:variable name="intIncrement" select="format-number($stnIndexIncrement * $DistConvFactor, $DecPl0, 'Standard')"/>

        <xsl:variable name="afterPlusDigits" select="string-length($intIncrement)"/>
        <xsl:variable name="afterPlusZeros" select="substring('000000000000', 1, $afterPlusDigits)"/>
        <xsl:variable name="afterPlusFmt" select="concat($afterPlusZeros, '.', substring-after($decPl, '.'))"/>

        <xsl:variable name="beforePlus" select="floor($absStnVal div ($stnIndexIncrement * $DistConvFactor))"/>
        <xsl:variable name="afterPlus" select="$absStnVal - $beforePlus * ($stnIndexIncrement * $DistConvFactor)"/>
        <xsl:value-of select="concat($signChar, format-number($beforePlus, '#0'), '+', format-number($afterPlus, $afterPlusFmt, 'Standard'))"/>
      </xsl:if>

      <xsl:if test="$includeUnitsAbbrev != 'false'">
        <xsl:value-of select="$distUnitAbbrev"/>
      </xsl:if>

      <xsl:if test="$zoneVal != ''">
        <xsl:value-of select="':'"/>
        <xsl:value-of select="format-number($zoneVal,'0')"/>
      </xsl:if>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return The Elevation At Specified Station ********** -->
<!-- **************************************************************** -->
<xsl:template name="ElevationAtStation">
  <xsl:param name="theStation"/>
  <xsl:param name="vertAlignment"/>

  <xsl:variable name="station">  <!-- Check for the passed in station value being within 0.0005 of the vertical alignment start or end station -->
    <xsl:variable name="startDelta" select="concat(substring('-',2 - (($theStation - msxsl:node-set($vertAlignment)/StartStation) &lt; 0)), '1') * ($theStation - msxsl:node-set($vertAlignment)/StartStation)"/>
    <xsl:variable name="endDelta" select="concat(substring('-',2 - (($theStation - msxsl:node-set($vertAlignment)/EndStation) &lt; 0)), '1') * ($theStation - msxsl:node-set($vertAlignment)/EndStation)"/>
    <xsl:choose>
      <xsl:when test="$startDelta &lt; 0.0005">
        <xsl:value-of select="msxsl:node-set($vertAlignment)/StartStation"/>
      </xsl:when>
      <xsl:when test="$endDelta &lt; 0.0005">
        <xsl:value-of select="msxsl:node-set($vertAlignment)/EndStation"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$theStation"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="($station &lt; msxsl:node-set($vertAlignment)/StartStation) or
                    ($station &gt; msxsl:node-set($vertAlignment)/EndStation)">
      <xsl:value-of select="''"/>  <!-- Return null -->
    </xsl:when>

    <xsl:otherwise>
      <xsl:for-each select="msxsl:node-set($vertAlignment)/*[(name(.) != 'StartStation') and (name(.) != 'EndStation')]">
        <xsl:variable name="stationIP" select="number(IntersectionPoint/Station)"/>
        <xsl:variable name="nextStnIP" select="number(following-sibling::*[1]/IntersectionPoint/Station)"/>
        <xsl:if test="($station &gt;= $stationIP) and (($station &lt; $nextStnIP) or (string(number($nextStnIP)) = 'NaN'))">
        <xsl:variable name="elevIP" select="IntersectionPoint/Elevation"/>
        <xsl:variable name="endStn">
          <xsl:choose>
            <xsl:when test="name(.) = 'VerticalPoint'">
              <xsl:value-of select="$stationIP"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="EndPoint/Station"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>
        <xsl:variable name="nextStartStn">
          <xsl:choose>
            <xsl:when test="name(following-sibling::*[1]) = 'VerticalPoint'">
              <xsl:value-of select="following-sibling::*[1]/IntersectionPoint/Station"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="following-sibling::*[1]/StartPoint/Station"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>
        <!-- We have located the vertical IP before or equal to the required station -->
        <xsl:choose>
          <!-- When at a vertical point simply return its elevation -->
          <xsl:when test="($station = $stationIP) and (name(.) = 'VerticalPoint')">
            <xsl:value-of select="$elevIP"/>
          </xsl:when>

          <!-- When on a grade compute the elevation along the grade -->
          <xsl:when test="($station &gt;= $endStn) and ($station &lt;= $nextStartStn)">
            <!-- In case the grade value recorded in the rxl file is incorrect (due to non-tangential -->
            <!-- vertical curves entered by start and end station and elevation values for example)   -->
            <!-- compute the grade based on the previous and next elevations and stations.            -->
            <xsl:variable name="endElev">
              <xsl:choose>
                <xsl:when test="name(.) = 'VerticalPoint'">
                  <xsl:value-of select="IntersectionPoint/Elevation"/>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:value-of select="EndPoint/Elevation"/>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:variable>

            <xsl:variable name="nextElev">
              <xsl:choose>
                <xsl:when test="name(following-sibling::*[1]) = 'VerticalPoint'">
                  <xsl:value-of select="following-sibling::*[1]/IntersectionPoint/Elevation"/>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:value-of select="following-sibling::*[1]/StartPoint/Elevation"/>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:variable>
            
            <xsl:variable name="grade">
              <xsl:variable name="computedGrade" select="($nextElev - $endElev) div ($nextStartStn - $endStn)"/>
              <xsl:choose>
                <xsl:when test="string(number($computedGrade)) != 'NaN'">
                  <xsl:value-of select="$computedGrade"/>
                </xsl:when>
                <xsl:otherwise>  <!-- Unable to compute grade - use value from file -->
                  <xsl:value-of select="GradeOut div 100.0"/>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:variable>

            <xsl:value-of select="$endElev + ($station - $endStn) * $grade"/>
          </xsl:when>

        <!-- When on the lead out section of this parabolic vertical curve compute the elevation on the curve -->
        <xsl:when test="((name(.) = 'VerticalParabola') or (name(.) = 'VerticalAsymmetricParabola')) and
                        ($station &lt;= $endStn)">
          <xsl:call-template name="ParabolaPointElevation">
            <xsl:with-param name="stationIP" select="$stationIP"/>
            <xsl:with-param name="gradeIn" select="GradeIn div 100.0"/>
            <xsl:with-param name="gradeOut" select="GradeOut div 100.0"/>
            <xsl:with-param name="startStn" select="StartPoint/Station"/>
            <xsl:with-param name="endStn" select="EndPoint/Station"/>
            <xsl:with-param name="startElev" select="StartPoint/Elevation"/>
            <xsl:with-param name="endElev" select="EndPoint/Elevation"/>
            <xsl:with-param name="lenIn" select="$stationIP - StartPoint/Station"/>
            <xsl:with-param name="lenOut" select="EndPoint/Station - $stationIP"/>
            <xsl:with-param name="ptStn" select="$station"/>
          </xsl:call-template>
        </xsl:when>

        <!-- When on the lead in section of next parabolic vertical curve compute the elevation on the curve -->
        <xsl:when test="((name(following-sibling::*[1]) = 'VerticalParabola') or
                         (name(following-sibling::*[1]) = 'VerticalAsymmetricParabola')) and
                        ($station &gt;= following-sibling::*[1]/StartPoint/Station)">
          <xsl:call-template name="ParabolaPointElevation">
            <xsl:with-param name="stationIP" select="$nextStnIP"/>
            <xsl:with-param name="gradeIn" select="following-sibling::*[1]/GradeIn div 100.0"/>
            <xsl:with-param name="gradeOut" select="following-sibling::*[1]/GradeOut div 100.0"/>
            <xsl:with-param name="startStn" select="following-sibling::*[1]/StartPoint/Station"/>
            <xsl:with-param name="endStn" select="following-sibling::*[1]/EndPoint/Station"/>
            <xsl:with-param name="startElev" select="following-sibling::*[1]/StartPoint/Elevation"/>
            <xsl:with-param name="endElev" select="following-sibling::*[1]/EndPoint/Elevation"/>
            <xsl:with-param name="lenIn" select="$nextStnIP - following-sibling::*[1]/StartPoint/Station"/>
            <xsl:with-param name="lenOut" select="following-sibling::*[1]/EndPoint/Station - $nextStnIP"/>
            <xsl:with-param name="ptStn" select="$station"/>
          </xsl:call-template>
        </xsl:when>

        <!-- When on the lead out section of this circular vertical curve compute the elevation on the curve -->
        <xsl:when test="(name(.) = 'VerticalArc') and ($station &lt;= $endStn)">
          <xsl:call-template name="CircularVertCurvePointElevation">
            <xsl:with-param name="centreStn" select="CentrePoint/Station"/>
            <xsl:with-param name="centreElev" select="CentrePoint/Elevation"/>
            <xsl:with-param name="intersectElev" select="IntersectionPoint/Elevation"/>
            <xsl:with-param name="radius" select="Radius"/>
            <xsl:with-param name="ptStn" select="$station"/>
          </xsl:call-template>
        </xsl:when>

        <!-- When on the lead in section of next circular vertical curve compute the elevation on the curve -->
        <xsl:when test="(name(following-sibling::*[1]) = 'VerticalArc') and
                        ($station &gt;= following-sibling::*[1]/StartPoint/Station)">
          <xsl:call-template name="CircularVertCurvePointElevation">
            <xsl:with-param name="centreStn" select="following-sibling::*[1]/CentrePoint/Station"/>
            <xsl:with-param name="centreElev" select="following-sibling::*[1]/CentrePoint/Elevation"/>
            <xsl:with-param name="intersectElev" select="following-sibling::*[1]/IntersectionPoint/Elevation"/>
            <xsl:with-param name="radius" select="following-sibling::*[1]/Radius"/>
            <xsl:with-param name="ptStn" select="$station"/>
          </xsl:call-template>
        </xsl:when>

      </xsl:choose>
    </xsl:if>
  </xsl:for-each>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return the position at the given station *********** -->
<!-- **************************************************************** -->
<xsl:template name="PositionAtStation">
  <xsl:param name="horizAlignment"/>
  <xsl:param name="station"/>

  <!-- This function returns a node set with north and east elements -->
  <!-- It uses the global $roadScaleFactor variable.                 -->
  <xsl:choose>
    <xsl:when test="$station &lt; msxsl:node-set($horizAlignment)/StartStation">Out of range</xsl:when>
    <xsl:when test="$station &gt; msxsl:node-set($horizAlignment)/EndStation">Out of range</xsl:when>
    <xsl:otherwise>
      <xsl:for-each select="msxsl:node-set($horizAlignment)/*[(name(.) != 'StartStation') and (name(.) != 'EndStation') and (name(.) != 'StartPoint')]">
        <xsl:if test="(($station &gt;= StartStation) and ($station &lt; EndStation) and (position() != last())) or
                      (($station &gt;= StartStation) and ($station &lt;= EndStation) and (position() = last()))">
          <xsl:choose>
            <xsl:when test="name(.) = 'Straight'">
              <xsl:call-template name="InterpolatedCoordinates">
                <xsl:with-param name="startN" select="StartCoordinate/North"/>
                <xsl:with-param name="startE" select="StartCoordinate/East"/>
                <xsl:with-param name="endN" select="EndCoordinate/North"/>
                <xsl:with-param name="endE" select="EndCoordinate/East"/>
                <xsl:with-param name="distAlong" select="($station - StartStation) * $roadScaleFactor"/>
              </xsl:call-template>
            </xsl:when>

            <xsl:when test="name(.) = 'Arc'">
              <xsl:variable name="distAlong" select="($station - StartStation) * $roadScaleFactor"/>
              <xsl:variable name="deflectionAngle" select="($distAlong div (Radius * $roadScaleFactor)) div 2.0"/>
              <xsl:variable name="sinDeflectionAngle">
                <xsl:call-template name="Sine">
                  <xsl:with-param name="theAngle" select="$deflectionAngle"/>
                </xsl:call-template>
              </xsl:variable>
              <xsl:variable name="chordLen" select="2.0 * Radius * $roadScaleFactor * $sinDeflectionAngle"/>
              <xsl:variable name="azimuth">
                <xsl:choose>
                  <xsl:when test="Direction = 'Right'">
                    <xsl:value-of select="StartAzimuth + $deflectionAngle * 180.0 div $Pi"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="StartAzimuth - $deflectionAngle * 180.0 div $Pi"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:variable>
              <xsl:call-template name="FollowAzimuth">
                <xsl:with-param name="azimuth" select="$azimuth"/>
                <xsl:with-param name="distance" select="$chordLen"/>
                <xsl:with-param name="startN" select="StartCoordinate/North"/>
                <xsl:with-param name="startE" select="StartCoordinate/East"/>
              </xsl:call-template>
            </xsl:when>

            <xsl:when test="name(.) = 'EntrySpiral'">
              <xsl:variable name="offsets">
                <xsl:call-template name="CalcSpiral">
                  <xsl:with-param name="smallRadius" select="EndRadius * $roadScaleFactor"/>
                  <xsl:with-param name="largeRadius" select="StartRadius * $roadScaleFactor"/>
                  <xsl:with-param name="length" select="Length * $roadScaleFactor"/>
                  <xsl:with-param name="spiralDist" select="($station - StartStation) * $roadScaleFactor"/>
                  <xsl:with-param name="spiralType" select="$spiralType"/>
                </xsl:call-template>
              </xsl:variable>
              
              <xsl:variable name="tempPos">
                <xsl:call-template name="FollowAzimuth">
                  <xsl:with-param name="azimuth" select="StartAzimuth"/>
                  <xsl:with-param name="distance" select="msxsl:node-set($offsets)/along"/>
                  <xsl:with-param name="startN" select="StartCoordinate/North"/>
                  <xsl:with-param name="startE" select="StartCoordinate/East"/>
                </xsl:call-template>
              </xsl:variable>

              <xsl:variable name="across">
                <xsl:choose>
                  <xsl:when test="Direction = 'Right'">
                    <xsl:value-of select="msxsl:node-set($offsets)/across"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="msxsl:node-set($offsets)/across * -1.0"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:variable>
              
              <xsl:call-template name="FollowAzimuth">
                <xsl:with-param name="azimuth" select="StartAzimuth + 90.0"/>
                <xsl:with-param name="distance" select="$across"/>
                <xsl:with-param name="startN" select="msxsl:node-set($tempPos)/north"/>
                <xsl:with-param name="startE" select="msxsl:node-set($tempPos)/east"/>
              </xsl:call-template>
            </xsl:when>

            <xsl:when test="name(.) = 'ExitSpiral'">
              <xsl:variable name="offsets">
                <xsl:call-template name="CalcSpiral">
                  <xsl:with-param name="smallRadius" select="StartRadius * $roadScaleFactor"/>
                  <xsl:with-param name="largeRadius" select="EndRadius * $roadScaleFactor"/>
                  <xsl:with-param name="length" select="Length * $roadScaleFactor"/>
                  <xsl:with-param name="spiralDist" select="(Length - ($station - StartStation)) * $roadScaleFactor"/>
                  <xsl:with-param name="spiralType" select="$spiralType"/>
                </xsl:call-template>
              </xsl:variable>

              <xsl:variable name="tempPos">
                <xsl:call-template name="FollowAzimuth">
                  <xsl:with-param name="azimuth" select="EndAzimuth + 180.0"/>
                  <xsl:with-param name="distance" select="msxsl:node-set($offsets)/along"/>
                  <xsl:with-param name="startN" select="EndCoordinate/North"/>
                  <xsl:with-param name="startE" select="EndCoordinate/East"/>
                </xsl:call-template>
              </xsl:variable>

              <xsl:variable name="across">
                <xsl:choose>
                  <xsl:when test="Direction = 'Right'">
                    <xsl:value-of select="msxsl:node-set($offsets)/across * -1.0"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="msxsl:node-set($offsets)/across"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:variable>

              <xsl:call-template name="FollowAzimuth">
                <xsl:with-param name="azimuth" select="EndAzimuth - 90.0"/>
                <xsl:with-param name="distance" select="$across"/>
                <xsl:with-param name="startN" select="msxsl:node-set($tempPos)/north"/>
                <xsl:with-param name="startE" select="msxsl:node-set($tempPos)/east"/>
              </xsl:call-template>
            </xsl:when>
          </xsl:choose>
        </xsl:if>
      </xsl:for-each>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****** Return the instantaneous azimuth given the station ****** -->
<!-- **************************************************************** -->
<xsl:template name="InstantaneousAzimuth">
  <xsl:param name="horizAlignment"/>
  <xsl:param name="station"/>

  <xsl:variable name="retAzimuth">
    <xsl:choose>
      <xsl:when test="$station &lt; msxsl:node-set($horizAlignment)/StartStation">Out of range</xsl:when>
      <xsl:when test="$station &gt; msxsl:node-set($horizAlignment)/EndStation">Out of range</xsl:when>
      <xsl:otherwise>
        <xsl:for-each select="msxsl:node-set($horizAlignment)/*[(name(.) != 'StartStation') and (name(.) != 'EndStation') and (name(.) != 'StartPoint')]">
          <xsl:variable name="isStartStn">
            <xsl:choose>
              <xsl:when test="concat(substring('-',2 - (($station - StartStation) &lt; 0)), '1') * ($station - StartStation) &lt; 0.001">true</xsl:when>
              <xsl:otherwise>false</xsl:otherwise>
            </xsl:choose>
          </xsl:variable>
          <xsl:variable name="isEndStn">
            <xsl:choose>
              <xsl:when test="concat(substring('-',2 - (($station - EndStation) &lt; 0)), '1') * ($station - EndStation) &lt; 0.001">true</xsl:when>
              <xsl:otherwise>false</xsl:otherwise>
            </xsl:choose>
          </xsl:variable>
          <xsl:variable name="rndStartStn" select="format-number(StartStation, $DecPl5, 'Standard')"/>
          <xsl:variable name="rndEndStn" select="format-number(EndStation, $DecPl5, 'Standard')"/>
          <xsl:if test="($isStartStn = 'true') or (($isEndStn = 'true') and (position() = last())) or
                        (($station &gt; $rndStartStn) and ($station &lt;= $rndEndStn) and (position() != last())) or
                        (($station &gt; $rndStartStn) and ($station &lt;= $rndEndStn))">
            <xsl:choose>
              <xsl:when test="name(.) = 'Straight'">
                <xsl:element name="azimuth">
                  <xsl:value-of select="StartAzimuth"/>
                </xsl:element>
              </xsl:when>

              <xsl:when test="name(.) = 'Arc'">
                <xsl:variable name="deltaAngle" select="(($station - StartStation) div Radius) * 180.0 div $Pi"/>
                <xsl:element name="azimuth">
                  <xsl:choose>
                    <xsl:when test="Direction = 'Right'">
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="StartAzimuth + $deltaAngle"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="StartAzimuth - $deltaAngle"/>
                      </xsl:call-template>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:element>
              </xsl:when>

              <xsl:when test="name(.) = 'EntrySpiral'">
                <xsl:variable name="deflection">
                  <xsl:choose>
                    <xsl:when test="$spiralType = 'NSWCubicParabola'">
                      <xsl:variable name="transitionXc">
                        <xsl:call-template name="CalcNSWTransitionXc">
                          <xsl:with-param name="length" select="Length"/>
                          <xsl:with-param name="smallRadius" select="EndRadius"/>
                          <xsl:with-param name="largeRadius" select="StartRadius"/>
                        </xsl:call-template>
                      </xsl:variable>

                      <xsl:call-template name="CalcNSWDeflectionAtDistance">
                        <xsl:with-param name="smallRadius" select="EndRadius"/>
                        <xsl:with-param name="largeRadius" select="StartRadius"/>
                        <xsl:with-param name="length" select="Length"/>
                        <xsl:with-param name="spiralDist" select="$station - StartStation"/>
                        <xsl:with-param name="transitionXc" select="$transitionXc"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise> <!-- Clothoid spiral, Cubic spiral, Bloss spiral, CubicParabola or KoreanCubicParabola -->
                      <xsl:variable name="spiralVals">
                        <xsl:call-template name="CalcSpiral">
                          <xsl:with-param name="smallRadius" select="EndRadius"/>
                          <xsl:with-param name="largeRadius" select="StartRadius"/>
                          <xsl:with-param name="length" select="Length"/>
                          <xsl:with-param name="spiralDist" select="$station - StartStation"/>
                          <xsl:with-param name="spiralType" select="$spiralType"/>
                        </xsl:call-template>
                      </xsl:variable>
                      <xsl:value-of select="msxsl:node-set($spiralVals)/deflection"/>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:variable>
                <xsl:element name="azimuth">
                  <xsl:choose>
                    <xsl:when test="Direction = 'Right'">
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="StartAzimuth + $deflection"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="StartAzimuth - $deflection"/>
                      </xsl:call-template>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:element>
              </xsl:when>

              <xsl:when test="name(.) = 'ExitSpiral'">
                <xsl:variable name="deflection">
                  <xsl:choose>
                    <xsl:when test="$spiralType = 'NSWCubicParabola'">
                      <xsl:variable name="transitionXc">
                        <xsl:call-template name="CalcNSWTransitionXc">
                          <xsl:with-param name="length" select="Length"/>
                          <xsl:with-param name="smallRadius" select="StartRadius"/>
                          <xsl:with-param name="largeRadius" select="EndRadius"/>
                        </xsl:call-template>
                      </xsl:variable>

                      <xsl:call-template name="CalcNSWDeflectionAtDistance">
                        <xsl:with-param name="smallRadius" select="StartRadius"/>
                        <xsl:with-param name="largeRadius" select="EndRadius"/>
                        <xsl:with-param name="length" select="Length"/>
                        <xsl:with-param name="spiralDist" select="Length - ($station - StartStation)"/>
                        <xsl:with-param name="transitionXc" select="$transitionXc"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise> <!-- Clothoid spiral, Cubic spiral, Bloss spiral, CubicParabola or KoreanCubicParabola -->
                      <xsl:variable name="spiralVals">
                        <xsl:call-template name="CalcSpiral">
                          <xsl:with-param name="smallRadius" select="StartRadius"/>
                          <xsl:with-param name="largeRadius" select="EndRadius"/>
                          <xsl:with-param name="length" select="Length"/>
                          <xsl:with-param name="spiralDist" select="Length - ($station - StartStation)"/>
                          <xsl:with-param name="spiralType" select="$spiralType"/>
                        </xsl:call-template>
                      </xsl:variable>
                      <xsl:value-of select="msxsl:node-set($spiralVals)/deflection"/>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:variable>
                <xsl:element name="azimuth">
                  <xsl:choose>
                    <xsl:when test="Direction = 'Right'">
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="EndAzimuth - $deflection"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:call-template name="NormalisedAngle">
                        <xsl:with-param name="angle" select="EndAzimuth + $deflection"/>
                      </xsl:call-template>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:element>
              </xsl:when>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:value-of select="msxsl:node-set($retAzimuth)/azimuth[1]"/>  <!-- Return only first azimuth value in case of an IP point very close to specified station -->
</xsl:template>


<!-- **************************************************************** -->
<!-- **** Return The Delta Elevation Value Interpolated By Grade **** -->
<!-- **************************************************************** -->
<xsl:template name="InterpolatedDeltaElevByGrade">
  <xsl:param name="prevXSDeltas"/>
  <xsl:param name="nextXSDeltas"/>
  <xsl:param name="station"/>
  <xsl:param name="prevTemplateStation"/>
  <xsl:param name="nextTemplateStation"/>
  <xsl:param name="currPos"/>

  <xsl:variable name="gradeInterpDeltas">
    <xsl:for-each select="msxsl:node-set($prevXSDeltas)/xsPos">
      <xsl:if test="position() &lt;= $currPos">
        <xsl:variable name="thisPos" select="position()"/>
        <xsl:variable name="prevXSGradeAndLengthToPos">  <!-- Grade and length of element to the current position on the previous cross-section -->
          <xsl:variable name="priorPtDeltaElev">
            <xsl:choose>
              <xsl:when test="position() = 1">0</xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="sum(msxsl:node-set($prevXSDeltas)/xsPos[position() &lt; $thisPos]/deltaElev)"/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:variable>

          <xsl:variable name="priorPtOffset">
            <xsl:choose>
              <xsl:when test="position() = 1">0</xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="sum(msxsl:node-set($prevXSDeltas)/xsPos[position() &lt; $thisPos]/deltaOffset)"/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:variable>

          <xsl:variable name="thisDeltaElev" select="sum(msxsl:node-set($prevXSDeltas)/xsPos[position() &lt;= $thisPos]/deltaElev)"/>
          <xsl:variable name="thisOffset" select="sum(msxsl:node-set($prevXSDeltas)/xsPos[position() &lt;= $thisPos]/deltaOffset)"/>

          <xsl:element name="deltaElevation" namespace="">
            <xsl:value-of select="$thisDeltaElev - $priorPtDeltaElev"/>
          </xsl:element>

          <xsl:element name="grade" namespace="">
            <xsl:variable name="deltaOffset" select="concat(substring('-',2 - (($thisOffset - $priorPtOffset) &lt; 0)), '1') * ($thisOffset - $priorPtOffset)"/>
            <xsl:if test="$deltaOffset &gt; 0.000001">  <!-- Guard against divide by zero -->
              <xsl:value-of select="($thisDeltaElev - $priorPtDeltaElev) div ($thisOffset - $priorPtOffset)"/>
            </xsl:if>
          </xsl:element>

          <xsl:element name="length" namespace="">
            <xsl:value-of select="$thisOffset - $priorPtOffset"/>
          </xsl:element>
        </xsl:variable>

        <xsl:variable name="nextXSGradeAndLengthToPos">  <!-- Grade and length of element to the current position on the next cross-section -->
          <xsl:variable name="priorPtDeltaElev">
            <xsl:choose>
              <xsl:when test="position() = 1">0</xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="sum(msxsl:node-set($nextXSDeltas)/xsPos[position() &lt; $thisPos]/deltaElev)"/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:variable>

          <xsl:variable name="priorPtOffset">
            <xsl:choose>
              <xsl:when test="position() = 1">0</xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="sum(msxsl:node-set($nextXSDeltas)/xsPos[position() &lt; $thisPos]/deltaOffset)"/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:variable>

          <xsl:variable name="thisDeltaElev" select="sum(msxsl:node-set($nextXSDeltas)/xsPos[position() &lt;= $thisPos]/deltaElev)"/>
          <xsl:variable name="thisOffset" select="sum(msxsl:node-set($nextXSDeltas)/xsPos[position() &lt;= $thisPos]/deltaOffset)"/>

          <xsl:element name="deltaElevation" namespace="">
            <xsl:value-of select="$thisDeltaElev - $priorPtDeltaElev"/>
          </xsl:element>

          <xsl:element name="grade" namespace="">
            <xsl:variable name="deltaOffset" select="concat(substring('-',2 - (($thisOffset - $priorPtOffset) &lt; 0)), '1') * ($thisOffset - $priorPtOffset)"/>
            <xsl:if test="$deltaOffset &gt; 0.000001">  <!-- Guard against divide by zero -->
              <xsl:value-of select="($thisDeltaElev - $priorPtDeltaElev) div ($thisOffset - $priorPtOffset)"/>
            </xsl:if>
          </xsl:element>

          <xsl:element name="length" namespace="">
            <xsl:value-of select="$thisOffset - $priorPtOffset"/>
          </xsl:element>
        </xsl:variable>

        <xsl:variable name="interpGrade">
          <xsl:call-template name="InterpolatedValueByStation">
            <xsl:with-param name="startValue" select="msxsl:node-set($prevXSGradeAndLengthToPos)/grade"/>
            <xsl:with-param name="endValue" select="msxsl:node-set($nextXSGradeAndLengthToPos)/grade"/>
            <xsl:with-param name="startStn" select="$prevTemplateStation"/>
            <xsl:with-param name="endStn" select="$nextTemplateStation"/>
            <xsl:with-param name="station" select="$station"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:variable name="interpLength">
          <xsl:call-template name="InterpolatedValueByStation">
            <xsl:with-param name="startValue" select="msxsl:node-set($prevXSGradeAndLengthToPos)/length"/>
            <xsl:with-param name="endValue" select="msxsl:node-set($nextXSGradeAndLengthToPos)/length"/>
            <xsl:with-param name="startStn" select="$prevTemplateStation"/>
            <xsl:with-param name="endStn" select="$nextTemplateStation"/>
            <xsl:with-param name="station" select="$station"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:element name="deltaElev" namespace="">
          <xsl:choose>
            <xsl:when test="string(number($interpGrade)) = 'NaN'">
              <!-- Unable to successfully determine interpolated grade and length probably due to a vertical element -->
              <!-- Revert to simple interpolation of the delta elevation values at each end.                         -->
              <xsl:call-template name="InterpolatedValueByStation">
                <xsl:with-param name="startValue" select="msxsl:node-set($prevXSGradeAndLengthToPos)/deltaElevation"/>
                <xsl:with-param name="endValue" select="msxsl:node-set($nextXSGradeAndLengthToPos)/deltaElevation"/>
                <xsl:with-param name="startStn" select="$prevTemplateStation"/>
                <xsl:with-param name="endStn" select="$nextTemplateStation"/>
                <xsl:with-param name="station" select="$station"/>
              </xsl:call-template>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$interpLength * $interpGrade"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>
      </xsl:if>
    </xsl:for-each>
  </xsl:variable>

  <xsl:value-of select="sum(msxsl:node-set($gradeInterpDeltas)/deltaElev)"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Get Previous and Next Template Names ************* -->
<!-- **************************************************************** -->
<xsl:template name="GetTemplateNames">
  <xsl:param name="station"/>
  <xsl:param name="templateAssignment"/>
    
  <!-- Get the previous and next template names for left and right sides based on current station -->
  <!-- Returns a node set with the following elements:
         prevLeftTemplateName
         prevRightTemplateName
         prevLeftTemplateStation
         prevRightTemplateStation
         nextLeftTemplateName
         nextRightTemplateName
         nextLeftTemplateStation
         nextRightTemplateStation
  -->
  
  <xsl:element name="prevLeftTemplateName" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &lt;= $station) and (LeftSide/Type != 'Interpolate')][last()]">
      <xsl:value-of select="LeftSide/Name"/>
    </xsl:for-each>
  </xsl:element>
  
  <xsl:element name="prevRightTemplateName" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &lt;= $station) and (RightSide/Type != 'Interpolate')][last()]">
      <xsl:value-of select="RightSide/Name"/>
    </xsl:for-each>
  </xsl:element>
  
  <xsl:element name="prevLeftTemplateStation" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &lt;= $station) and (LeftSide/Type != 'Interpolate')][last()]">
      <xsl:value-of select="Station"/>
    </xsl:for-each>
  </xsl:element>

  <xsl:element name="prevRightTemplateStation" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &lt;= $station) and (RightSide/Type != 'Interpolate')][last()]">
      <xsl:value-of select="Station"/>
    </xsl:for-each>
  </xsl:element>

  <xsl:element name="nextLeftTemplateName" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &gt;= $station) and (LeftSide/Type != 'Interpolate')][1]">
      <xsl:value-of select="LeftSide/Name"/>
    </xsl:for-each>
  </xsl:element>

  <xsl:element name="nextRightTemplateName" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &gt;= $station) and (RightSide/Type != 'Interpolate')][1]">
      <xsl:value-of select="RightSide/Name"/>
    </xsl:for-each>
  </xsl:element>

  <xsl:element name="nextLeftTemplateStation" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &gt;= $station) and (LeftSide/Type != 'Interpolate')][1]">
      <xsl:value-of select="Station"/>
    </xsl:for-each>
  </xsl:element>

  <xsl:element name="nextRightTemplateStation" namespace="">
    <xsl:for-each select="msxsl:node-set($templateAssignment)/ApplyTemplates[(Station &gt;= $station) and (RightSide/Type != 'Interpolate')][1]">
      <xsl:value-of select="Station"/>
    </xsl:for-each>
  </xsl:element>

</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Get Template Delta Values ******************* -->
<!-- **************************************************************** -->
<xsl:template name="GetTemplateDeltas">
  <xsl:param name="templates"/>
  <xsl:param name="templateNames"/>
  <xsl:param name="templateName"/>
  <xsl:param name="station"/>
  <xsl:param name="superWideningAssignment"/>
  <xsl:param name="side"/>
  <xsl:param name="prev"/>
  <xsl:param name="includeSideSlopeElements" select="'false'"/>
  
  <!-- This template computes the deltas across the specified template including the   -->
  <!-- application of the superelevation and widening at the assigned template station -->
  <!-- (not necessarily the current station) and returns a node set of cross-section   -->
  <!-- position delta values as follows:
          <xsPos>
            <deltaElev>number</deltaElev>
            <deltaOffset>number</deltaOffset>
            <code>string</code>
            <clElevAdj>
              <value>number</value>     the centreline elevation adjustment for the template
              <prevStn>number</prevStn> the station of the previous template assignment
              <nextStn>number</nextStn> the station of the next template assignment
            </clElevAdj>
          </xsPos>

       If there is a side slope element defined and $includeSideSlopeElements is not 'false' 
       this will be added as a sideSlope element
          <SideSlope>
            <Code>string</Code>
            <CutGrade>number</CutGrade>
            <FillGrade>number</FillGrade>
            <CutDitchWidth>number</CutDitchWidth>
          </SideSlope>
  -->

  <!-- Get a node set of the superelevation and widening values (interpolated -->
  <!-- if required) for both sides at the specified station.                  -->
  <xsl:variable name="allSuperWideningVals">
    <xsl:call-template name="GetSuperWidening">
      <xsl:with-param name="station" select="$station"/>
      <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
    </xsl:call-template>
  </xsl:variable>

  <!-- Now grab the superelevation and widening details that apply to this side -->
  <xsl:variable name="superWideningVals">
    <xsl:element name="pivot" namespace="">
      <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/pivot"/>
    </xsl:element>
    <xsl:choose>
      <xsl:when test="$side = 'Left'">  <!-- Get the left side values -->
        <xsl:element name="super" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/leftSuper"/>
        </xsl:element>

        <xsl:element name="widening" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/leftWidening"/>
        </xsl:element>
      </xsl:when>

      <xsl:otherwise>  <!-- Get the right side values -->
        <xsl:element name="super" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/rightSuper"/>
        </xsl:element>

        <xsl:element name="widening" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/rightWidening"/>
        </xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Compute the centreline vertical adjustment required for left and right pivot superelevation -->
  <!-- definitions.  This is done by computing the template deltas without superelevation applied  -->
  <!-- but with any widening applied, then computing the deltas with both superelevation and       -->
  <!-- widening applied and returning the elevation difference between the sums of the elevation   -->
  <!-- deltas from each application.  The superelevation and widening values used are those that   -->
  <!-- apply at the actual station of interest.                                                    -->
  <xsl:variable name="clElevAdj">  <!-- The centreline elevation may need to be adjusted in the case of left or right superelevation pivot points -->
    <xsl:choose>
      <xsl:when test="msxsl:node-set($superWideningVals)/pivot = 'Crown'">0</xsl:when> <!-- No centreline elevation adjustment when pivoting about the crown -->
      <xsl:otherwise>
        <xsl:call-template name="ComputeCLElevAdj">
          <xsl:with-param name="station" select="$station"/>
          <xsl:with-param name="templates" select="$templates"/>
          <xsl:with-param name="templateNames" select="$templateNames"/>
          <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
          <xsl:with-param name="pivot" select="msxsl:node-set($superWideningVals)/pivot"/>
          <xsl:with-param name="prev" select="$prev"/>  <!-- Pass through whether we are interested in the previous or next template -->
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Retain the station of the previous and next templates on the pivot side so that -->
  <!-- they can be used later for interpolation purposes - the values are passed back  -->
  <!-- with the computed centreline elevation correction.                              -->
  <xsl:variable name="clElevAdjPrevStn">
    <xsl:choose>
      <xsl:when test="msxsl:node-set($superWideningVals)/pivot = 'Left'">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevLeftTemplateStation"/>
      </xsl:when>

      <xsl:when test="msxsl:node-set($superWideningVals)/pivot = 'Right'">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevRightTemplateStation"/>
      </xsl:when>

      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="clElevAdjNextStn">
    <xsl:choose>
      <xsl:when test="msxsl:node-set($superWideningVals)/pivot = 'Left'">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextLeftTemplateStation"/>
      </xsl:when>

      <xsl:when test="msxsl:node-set($superWideningVals)/pivot = 'Right'">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextRightTemplateStation"/>
      </xsl:when>

      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="firstSuperedElement">
    <xsl:for-each select="msxsl:node-set($templates)/Template[Name = $templateName]/*[(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">
      <xsl:if test="(ApplySuperelevation = 'true') and (count(preceding-sibling::*[ApplySuperelevation = 'true']) = 0)">
        <!-- This element has super switched on and no preceding elements had super switched on -->
        <xsl:element name="position" namespace="">
          <xsl:value-of select="position()"/>
        </xsl:element>

        <xsl:element name="deltaGrade" namespace="">
          <xsl:variable name="origGrade">
            <xsl:call-template name="ElementGrade">
              <xsl:with-param name="templateElement" select="."/>
            </xsl:call-template>
          </xsl:variable>

          <xsl:value-of select="msxsl:node-set($superWideningVals)/super - $origGrade"/>
        </xsl:element>
      </xsl:if>
    </xsl:for-each>
  </xsl:variable>

  <!-- Now compute the sets of deltas across the template applying the appropriate -->
  <!-- superelevation and widening.                                                -->
  <xsl:for-each select="msxsl:node-set($templates)/Template[Name = $templateName]">
    <xsl:for-each select="*[(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">

      <xsl:variable name="widenedDist">
        <xsl:choose>
          <xsl:when test="ApplyWidening = 'true'">
            <xsl:value-of select="HorizontalDistance + msxsl:node-set($superWideningVals)/widening"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="HorizontalDistance"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:variable>

      <!-- Apply any superelevation to the grade -->
      <xsl:variable name="superGrade">
        <xsl:call-template name="SuperelevatedGrade">
          <xsl:with-param name="superWideningVals" select="$superWideningVals"/>
          <xsl:with-param name="template" select="parent::Template"/>
          <xsl:with-param name="templateElement" select="."/>
          <xsl:with-param name="firstSuperedElement" select="$firstSuperedElement"/>
          <xsl:with-param name="widenedDist" select="$widenedDist"/>
          <xsl:with-param name="position" select="position()"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:element name="xsPos" namespace="">
        <xsl:element name="deltaElev" namespace="">
          <xsl:choose>
            <xsl:when test="string(number($superGrade)) = 'NaN'">  <!-- No grade - must be vertical -->
              <xsl:value-of select="VerticalDistance"/>            <!-- Use the VerticalDistance value -->
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$widenedDist * $superGrade div 100.0"/>  <!-- Apply superelevated grade to widened horiz distance -->
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>

        <xsl:element name="deltaOffset" namespace="">
          <xsl:value-of select="$widenedDist"/>
        </xsl:element>

        <xsl:element name="code" namespace="">
          <xsl:value-of select="Code"/>
        </xsl:element>

        <xsl:element name="clElevAdj" namespace="">
          <xsl:element name="value" namespace="">
            <xsl:value-of select="$clElevAdj"/>
          </xsl:element>
          <xsl:element name="prevStn" namespace="">
            <xsl:value-of select="$clElevAdjPrevStn"/>
          </xsl:element>
          <xsl:element name="nextStn" namespace="">
            <xsl:value-of select="$clElevAdjNextStn"/>
          </xsl:element>
        </xsl:element>
      </xsl:element>
    </xsl:for-each>
    
    <xsl:if test="$includeSideSlopeElements != 'false'">
      <xsl:for-each select="*[name(.) = 'SideSlope']">
        <xsl:copy-of select="."/>
      </xsl:for-each>
    </xsl:if>
  </xsl:for-each>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Return a Reverse Order Node Set Variable ************ -->
<!-- **************************************************************** -->
<xsl:template name="ReversedNodeSet">
  <xsl:param name="originalNodeSet"/>
  <xsl:param name="count"/>   <!-- Pass in the count of the elements in the node set -->
  <xsl:param name="item"/>    <!-- Initially set this equal to the element count     -->

  <!-- This recursive function will return the passed in node set in the reverse order -->
  <xsl:if test="$item &gt; 0">
    <xsl:choose>
      <xsl:when test="$item = $count">
        <xsl:for-each select="msxsl:node-set($originalNodeSet)/*[last()]">  <!-- Get the last element (returned first) -->
          <xsl:copy>
            <xsl:copy-of select="* | @*"/>
            <xsl:if test="text()">
              <xsl:value-of select="."/>
             </xsl:if>
          </xsl:copy>
        </xsl:for-each>
      </xsl:when>

      <xsl:otherwise>  <!-- Copy the appropriate preceding element -->
        <xsl:for-each select="msxsl:node-set($originalNodeSet)/*[last()]">  <!-- Get the last element -->
          <xsl:for-each select="preceding-sibling::*[$count - $item]">      <!-- get the required preceding element -->
            <xsl:copy>
              <xsl:copy-of select="* | @*"/>
              <xsl:if test="text()">
                <xsl:value-of select="."/>
               </xsl:if>
            </xsl:copy>
          </xsl:for-each>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>

    <!-- Recurse the function decrementing the item value -->
    <xsl:call-template name="ReversedNodeSet">
      <xsl:with-param name="originalNodeSet" select="$originalNodeSet"/>
      <xsl:with-param name="count" select="$count"/>
      <xsl:with-param name="item" select="$item - 1"/>
    </xsl:call-template>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- ** Calculate NSWCubicParabola deflection at dist along spiral ** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWDeflectionAtDistance">
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>
  <xsl:param name="length"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="transitionXc"/>

  <xsl:variable name="deflectionAtLargeRadius">
    <xsl:choose>
      <xsl:when test="string(number($largeRadius)) = 'NaN'">0</xsl:when>  <!-- Standard spiral to infinity -->
      <xsl:otherwise>
        <xsl:variable name="largeRadiusVals">  <!-- Get the along value at the large radius (spiralDist = 0) -->
          <xsl:call-template name="CalcNSWRadiusAtDistance">
            <xsl:with-param name="smallRadius" select="$smallRadius"/>
            <xsl:with-param name="largeRadius" select="$largeRadius"/>
            <xsl:with-param name="length" select="$length"/>
            <xsl:with-param name="spiralDist" select="0"/>
            <xsl:with-param name="transitionXc" select="$transitionXc"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:call-template name="CalcNSWSpiralDeflection">  <!-- Returned in degrees -->
          <xsl:with-param name="smallRadius" select="$largeRadius"/>
          <xsl:with-param name="transitionXc" select="msxsl:node-set($largeRadiusVals)/along"/>
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$spiralDist &lt; 0.00005">0</xsl:when>

    <xsl:when test="concat(substring('-',2 - (($length - $spiralDist) &lt; 0)), '1') * ($length - $spiralDist) &lt; 0.00005">
      <!-- At the smallest radius for the spiral -->
      <xsl:variable name="deflection">
        <xsl:call-template name="CalcNSWSpiralDeflection">  <!-- Returned in degrees -->
          <xsl:with-param name="smallRadius" select="$smallRadius"/>
          <xsl:with-param name="transitionXc" select="$transitionXc"/>
        </xsl:call-template>
      </xsl:variable>
      
      <!-- Return the deflection less the deflectionAtLargeRadius -->
      <xsl:value-of select="$deflection - $deflectionAtLargeRadius"/>
    </xsl:when>

    <xsl:otherwise>
      <!-- First get the radius at this position -->
      <xsl:variable name="radiusVals">
        <xsl:call-template name="CalcNSWRadiusAtDistance">
          <xsl:with-param name="smallRadius" select="$smallRadius"/>
          <xsl:with-param name="largeRadius" select="$largeRadius"/>
          <xsl:with-param name="length" select="$length"/>
          <xsl:with-param name="spiralDist" select="$spiralDist"/>
          <xsl:with-param name="transitionXc" select="$transitionXc"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="deflection">
        <xsl:call-template name="CalcNSWSpiralDeflection">  <!-- Returned in degrees -->
          <xsl:with-param name="smallRadius" select="msxsl:node-set($radiusVals)/radius"/>
          <xsl:with-param name="transitionXc" select="msxsl:node-set($radiusVals)/along"/>
        </xsl:call-template>
      </xsl:variable>

      <!-- Return the deflection less the deflectionAtLargeRadius -->
      <xsl:value-of select="$deflection - $deflectionAtLargeRadius"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Calculate NSWCubicParabola transitionXc value ******** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWTransitionXc">
  <xsl:param name="length"/>
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>

  <xsl:choose>
    <xsl:when test="string(number($largeRadius)) = 'NaN'">  <!-- Standard fully developed transition -->
      <xsl:call-template name="CalcNSWIterateXcStandard">
        <xsl:with-param name="transitionXc" select="$length * 0.99"/>  <!-- Initial estimate of TransitionXc value -->
        <xsl:with-param name="length" select="$length"/>
        <xsl:with-param name="smallRadius" select="$smallRadius"/>
      </xsl:call-template>
    </xsl:when>
    
    <xsl:otherwise>  <!-- Compound transition between 2 arcs -->
      <xsl:call-template name="CalcNSWIterateXcCompound">
        <xsl:with-param name="transitionXc" select="$smallRadius * 0.68"/>  <!-- Initial estimate of TransitionXc value -->
        <xsl:with-param name="length" select="$length"/>
        <xsl:with-param name="smallRadius" select="$smallRadius"/>
        <xsl:with-param name="largeRadius" select="$largeRadius"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Calculate spiral deltas ******************* -->
<!-- **************************************************************** -->
<xsl:template name="CalcSpiral">
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>
  <xsl:param name="length"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="spiralType" select="'Clothoid'"/>  <!-- Can be 'Clothoid', 'Cubic', 'Bloss', 'KoreanCubicParabola' or 'NSWCubicParabola' -->

  <!-- Returns node-set variable with the elements:  -->
  <!--   along                                       -->
  <!--   across                                      -->
  <!--   deflection                                  -->

  <xsl:if test="(string(number($length)) != 'NaN') and (string(number($smallRadius)) != 'NaN') and
                (string(number($spiralDist)) != 'NaN') and ($spiralDist &gt;= 0) and ($spiralDist &lt;= $length)">
    <!-- We have valid input values -->
    <xsl:choose>
      <xsl:when test="($spiralDist = 0.0) or ($smallRadius = 0.0)">
        <xsl:element name="along" namespace="">0</xsl:element>
        <xsl:element name="across" namespace="">0</xsl:element>
        <xsl:element name="deflection" namespace="">0</xsl:element>
      </xsl:when>

      <xsl:when test="string(number($largeRadius)) = 'NaN'">  <!-- Standard spiral calculation -->
        <xsl:variable name="K" select="$smallRadius * $length"/>

        <xsl:variable name="transitionXc">
          <xsl:if test="$spiralType = 'NSWCubicParabola'">
            <xsl:call-template name="CalcNSWTransitionXc">
              <xsl:with-param name="length" select="$length"/>
              <xsl:with-param name="smallRadius" select="$smallRadius"/>
              <xsl:with-param name="largeRadius" select="$largeRadius"/>
            </xsl:call-template>
          </xsl:if>
        </xsl:variable>

        <xsl:variable name="deflectionNSW">  <!-- Returned in degrees -->
          <xsl:if test="$spiralType = 'NSWCubicParabola'">
            <xsl:call-template name="CalcNSWSpiralDeflection">
              <xsl:with-param name="smallRadius" select="$smallRadius"/>
              <xsl:with-param name="transitionXc" select="$transitionXc"/>
            </xsl:call-template>
          </xsl:if>
        </xsl:variable>

        <xsl:variable name="spiralM">
          <xsl:if test="$spiralType = 'NSWCubicParabola'">
            <xsl:variable name="tanDeflection">
              <xsl:call-template name="Tan">
                <xsl:with-param name="theAngle" select="$deflectionNSW * $Pi div 180.0"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="$tanDeflection div (3.0 * $transitionXc * $transitionXc)"/>
          </xsl:if>
        </xsl:variable>

        <xsl:variable name="spiralVals">
          <xsl:call-template name="CalcSpiralXY">
            <xsl:with-param name="spiralDist" select="$spiralDist"/>
            <xsl:with-param name="K" select="$K"/>
            <xsl:with-param name="spiralM" select="$spiralM"/>
            <xsl:with-param name="spiralType" select="$spiralType"/>
            <xsl:with-param name="smallRadius" select="$smallRadius"/>
            <xsl:with-param name="length" select="$length"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:element name="along" namespace="">
          <xsl:value-of select="msxsl:node-set($spiralVals)/along"/>
        </xsl:element>

        <xsl:element name="across" namespace="">
          <xsl:value-of select="msxsl:node-set($spiralVals)/across"/>
        </xsl:element>

        <!-- Now compute the spiral deflection - returned in decimal degrees -->
        <xsl:element name="deflection" namespace="">
          <xsl:choose>
            <xsl:when test="$spiralType = 'NSWCubicParabola'">
              <xsl:value-of select="$deflectionNSW"/>
            </xsl:when>

            <xsl:otherwise>
              <xsl:call-template name="CalcSpiralDeflection">
                <xsl:with-param name="smallRadius" select="$smallRadius"/>
                <xsl:with-param name="largeRadius" select="$largeRadius"/>
                <xsl:with-param name="length" select="$length"/>
                <xsl:with-param name="spiralDist" select="$spiralDist"/>
                <xsl:with-param name="along" select="msxsl:node-set($spiralVals)/along"/>
                <xsl:with-param name="spiralType" select="$spiralType"/>
              </xsl:call-template>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>
      </xsl:when>

      <xsl:otherwise>  <!-- Spiral between 2 arcs (only applies to Clothoid spiral, Cubic spiral and NSWCubicParabola spirals) -->
        <xsl:choose>
          <xsl:when test="$largeRadius != $smallRadius">
            <xsl:choose>
              <xsl:when test="($spiralType = 'Clothoid') or ($spiralType = 'Cubic')">
                <xsl:variable name="K" select="($smallRadius * $largeRadius * $length) div ($largeRadius - $smallRadius)"/>
                <xsl:variable name="prevLength" select="concat(substring('-',2 - (($K div $smallRadius) &lt; 0)), '1') * ($K div $smallRadius) - $length"/>
                <xsl:variable name="localDist" select="$prevLength + $spiralDist"/>
                <xsl:variable name="startDeflection" select="($prevLength * $prevLength) div (2.0 * $K)"/>

                <xsl:variable name="startDeflectionX">
                  <xsl:call-template name="Cosine">
                    <xsl:with-param name="theAngle" select="$startDeflection"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="startDeflectionY">
                  <xsl:call-template name="Sine">
                    <xsl:with-param name="theAngle" select="$startDeflection"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="prevLenVals">
                  <xsl:call-template name="CalcSpiralXY">
                    <xsl:with-param name="spiralDist" select="$prevLength"/>
                    <xsl:with-param name="K" select="$K"/>
                    <xsl:with-param name="spiralType" select="$spiralType"/>
                    <xsl:with-param name="smallRadius" select="$smallRadius"/>
                    <xsl:with-param name="length" select="$length"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="localDistVals">
                  <xsl:call-template name="CalcSpiralXY">
                    <xsl:with-param name="spiralDist" select="$localDist"/>
                    <xsl:with-param name="K" select="$K"/>
                    <xsl:with-param name="spiralType" select="$spiralType"/>
                    <xsl:with-param name="smallRadius" select="$smallRadius"/>
                    <xsl:with-param name="length" select="$length"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="hX" select="msxsl:node-set($localDistVals)/along - msxsl:node-set($prevLenVals)/along"/>
                <xsl:variable name="hY" select="msxsl:node-set($localDistVals)/across - msxsl:node-set($prevLenVals)/across"/>

                <xsl:variable name="along" select="$hX * $startDeflectionX + $hY * $startDeflectionY"/>

                <xsl:variable name="hX2" select="$hX - $along * $startDeflectionX"/>
                <xsl:variable name="hY2" select="$hY - $along * $startDeflectionY"/>

                <xsl:element name="along" namespace="">  <!-- along value to be returned -->
                  <xsl:value-of select="$along"/>
                </xsl:element>

                <xsl:element name="across" namespace=""> <!-- across value to be returned -->
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="$hX2 * $hX2 + $hY2 * $hY2"/>
                  </xsl:call-template>
                </xsl:element>

                <xsl:element name="deflection" namespace="">
                  <!-- Could call the CalcSpiralDeflection template but we already have all the required values so compute it directly -->
                  <xsl:value-of select="(($localDist * $localDist) div (2.0 * $K) - $startDeflection) * 180.0 div $Pi"/>
                </xsl:element>
              </xsl:when>
              
              <xsl:when test="$spiralType = 'NSWCubicParabola'">  <!-- NSWCubicParabola type transition -->
                <xsl:variable name="transitionXc">
                  <xsl:call-template name="CalcNSWTransitionXc">
                    <xsl:with-param name="length" select="$length"/>
                    <xsl:with-param name="smallRadius" select="$smallRadius"/>
                    <xsl:with-param name="largeRadius" select="$largeRadius"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="fullDeflection">
                  <xsl:call-template name="CalcNSWSpiralDeflection">  <!-- Returned in degrees -->
                    <xsl:with-param name="smallRadius" select="$smallRadius"/>
                    <xsl:with-param name="transitionXc" select="$transitionXc"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="spiralM">
                  <xsl:variable name="tanDeflection">
                    <xsl:call-template name="Tan">
                      <xsl:with-param name="theAngle" select="$fullDeflection * $Pi div 180.0"/>
                    </xsl:call-template>
                  </xsl:variable>
                  <xsl:value-of select="$tanDeflection div (3.0 * $transitionXc * $transitionXc)"/>
                </xsl:variable>

                <xsl:variable name="deflection">
                  <xsl:call-template name="CalcNSWDeflectionAtDistance">
                    <xsl:with-param name="smallRadius" select="$smallRadius"/>
                    <xsl:with-param name="largeRadius" select="$largeRadius"/>
                    <xsl:with-param name="length" select="$length"/>
                    <xsl:with-param name="spiralDist" select="$spiralDist"/>
                    <xsl:with-param name="transitionXc" select="$transitionXc"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="fullyDevelopedLength">
                  <xsl:call-template name="CalcNSWSpiralLength">
                    <xsl:with-param name="transitionXc" select="$transitionXc"/>
                    <xsl:with-param name="spiralM" select="$spiralM"/>
                  </xsl:call-template>
                </xsl:variable>
                
                <xsl:variable name="prevLength" select="$fullyDevelopedLength - $length"/>
                <xsl:variable name="localDist" select="$prevLength + $spiralDist"/>

                <xsl:variable name="localDistVals">
                  <xsl:call-template name="CalcNSWSpiralXY">
                    <xsl:with-param name="spiralDist" select="$localDist"/>
                    <xsl:with-param name="spiralM" select="$spiralM"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="prevLenVals">
                  <xsl:call-template name="CalcNSWSpiralXY">
                    <xsl:with-param name="spiralDist" select="$prevLength"/>
                    <xsl:with-param name="spiralM" select="$spiralM"/>
                  </xsl:call-template>
                </xsl:variable>
                
                <xsl:variable name="startDeflection">
                  <xsl:call-template name="ArcTanSeries">
                    <xsl:with-param name="tanVal" select="3.0 * $spiralM * msxsl:node-set($prevLenVals)/along * msxsl:node-set($prevLenVals)/along"/>
                  </xsl:call-template>
                </xsl:variable>
                
                <xsl:variable name="startDeflectionX">
                  <xsl:call-template name="Cosine">
                    <xsl:with-param name="theAngle" select="$startDeflection"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="startDeflectionY">
                  <xsl:call-template name="Sine">
                    <xsl:with-param name="theAngle" select="$startDeflection"/>
                  </xsl:call-template>
                </xsl:variable>

                <xsl:variable name="hX" select="msxsl:node-set($localDistVals)/along - msxsl:node-set($prevLenVals)/along"/>
                <xsl:variable name="hY" select="msxsl:node-set($localDistVals)/across - msxsl:node-set($prevLenVals)/across"/>

                <xsl:variable name="along" select="$hX * $startDeflectionX + $hY * $startDeflectionY"/>

                <xsl:variable name="hX2" select="$hX - $along * $startDeflectionX"/>
                <xsl:variable name="hY2" select="$hY - $along * $startDeflectionY"/>

                <xsl:element name="along" namespace="">  <!-- along value to be returned -->
                  <xsl:value-of select="$along"/>
                </xsl:element>

                <xsl:element name="across" namespace=""> <!-- across value to be returned -->
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="$hX2 * $hX2 + $hY2 * $hY2"/>
                  </xsl:call-template>
                </xsl:element>
                
                <xsl:element name="deflection" namespace="">
                  <xsl:value-of select="$deflection - $startDeflection"/>
                </xsl:element>
              </xsl:when>
            </xsl:choose>
          </xsl:when>

          <xsl:otherwise>   <!-- This is a special case of an arc -->
            <xsl:variable name="deflectionAngle" select="$length div $smallRadius"/>

            <xsl:variable name="sinDeflection">
              <xsl:call-template name="Sine">
                <xsl:with-param name="theAngle" select="$deflectionAngle"/>
              </xsl:call-template>
            </xsl:variable>

            <xsl:variable name="cosDeflection">
              <xsl:call-template name="Cosine">
                <xsl:with-param name="theAngle" select="$deflectionAngle"/>
              </xsl:call-template>
            </xsl:variable>

            <xsl:element name="along" namespace="">
              <xsl:value-of select="$sinDeflection * $smallRadius"/>
            </xsl:element>

            <xsl:element name="across" namespace="">
              <xsl:value-of select="$smallRadius - $cosDeflection * $smallRadius"/>
            </xsl:element>

            <xsl:element name="deflection" namespace="">
              <xsl:value-of select="$deflectionAngle * 180.0 div $Pi"/>
            </xsl:element>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Compute Interpolated Coordinates *************** -->
<!-- **************************************************************** -->
<xsl:template name="InterpolatedCoordinates">
  <xsl:param name="startN"/>
  <xsl:param name="startE"/>
  <xsl:param name="endN"/>
  <xsl:param name="endE"/>
  <xsl:param name="distAlong"/>
  
  <xsl:variable name="totalLen">
    <xsl:call-template name="InverseDistance">
      <xsl:with-param name="deltaN" select="$endN - $startN"/>
      <xsl:with-param name="deltaE" select="$endE - $startE"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:element name="north" namespace="">
    <xsl:value-of select="($endN - $startN) * $distAlong div $totalLen + $startN"/>
  </xsl:element>

  <xsl:element name="east" namespace="">
    <xsl:value-of select="($endE - $startE) * $distAlong div $totalLen + $startE"/>
  </xsl:element>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Return the sine of an angle in radians ************ -->
<!-- **************************************************************** -->
<xsl:template name="Sine">
  <xsl:param name="theAngle"/>
  <xsl:variable name="normalisedAngle">
    <xsl:call-template name="RadianAngleBetweenLimits">
      <xsl:with-param name="anAngle" select="$theAngle"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="theSine">
    <xsl:call-template name="sineIter">
      <xsl:with-param name="pX2" select="$normalisedAngle * $normalisedAngle"/>
      <xsl:with-param name="pRslt" select="$normalisedAngle"/>
      <xsl:with-param name="pElem" select="$normalisedAngle"/>
      <xsl:with-param name="pN" select="1"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="number($theSine)"/>
</xsl:template>

<xsl:template name="sineIter">
  <xsl:param name="pX2"/>
  <xsl:param name="pRslt"/>
  <xsl:param name="pElem"/>
  <xsl:param name="pN"/>
  <xsl:param name="pEps" select="0.00000001"/>
  <xsl:variable name="vnextN" select="$pN+2"/>
  <xsl:variable name="vnewElem"  select="-$pElem*$pX2 div ($vnextN*($vnextN - 1))"/>
  <xsl:variable name="vnewResult" select="$pRslt + $vnewElem"/>
  <xsl:variable name="vdiffResult" select="$vnewResult - $pRslt"/>
  <xsl:choose>
    <xsl:when test="$vdiffResult > $pEps or $vdiffResult &lt; -$pEps">
      <xsl:call-template name="sineIter">
        <xsl:with-param name="pX2" select="$pX2"/>
        <xsl:with-param name="pRslt" select="$vnewResult"/>
        <xsl:with-param name="pElem" select="$vnewElem"/>
        <xsl:with-param name="pN" select="$vnextN"/>
        <xsl:with-param name="pEps" select="$pEps"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$vnewResult"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return the Cosine of an angle in radians *********** -->
<!-- **************************************************************** -->
<xsl:template name="Cosine">
  <xsl:param name="theAngle"/>

  <!-- Use the sine function after subtracting the angle from halfPi -->
  <xsl:call-template name="Sine">
    <xsl:with-param name="theAngle" select="$halfPi - $theAngle"/>
  </xsl:call-template>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return The Elevation Of A Point On A Parabola ******** -->
<!-- **************************************************************** -->
<xsl:template name="ParabolaPointElevation">
  <xsl:param name="stationIP"/>
  <xsl:param name="gradeIn"/>
  <xsl:param name="gradeOut"/>
  <xsl:param name="startStn"/>
  <xsl:param name="endStn"/>
  <xsl:param name="startElev"/>
  <xsl:param name="endElev"/>
  <xsl:param name="lenIn"/>
  <xsl:param name="lenOut"/>
  <xsl:param name="ptStn"/>

  <xsl:variable name="aOne">
    <xsl:choose>
      <xsl:when test="$lenIn + $lenOut &gt; 0.0">
        <xsl:value-of select="($gradeOut - $gradeIn) * $lenOut div ($lenIn + $lenOut)"/>
      </xsl:when>
      <xsl:otherwise>0.0</xsl:otherwise>  <!-- avoid divide by zero -->
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="aTwo">
    <xsl:choose>
      <xsl:when test="$lenIn + $lenOut &gt; 0.0">
        <xsl:value-of select="($gradeOut - $gradeIn) * $lenIn div ($lenIn + $lenOut)"/>
      </xsl:when>
      <xsl:otherwise>0.0</xsl:otherwise>  <!-- avoid divide by zero -->
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="xE" select="$ptStn - $startStn"/>
  <xsl:variable name="xX" select="$ptStn - $endStn"/>

  <xsl:choose>
    <xsl:when test="$ptStn &lt; $stationIP">
      <xsl:choose>
        <xsl:when test="$lenIn != 0.0">
          <xsl:value-of select="$startElev + $gradeIn * $xE + $aOne * $xE * $xE div (2.0 * $lenIn)"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="$startElev + $gradeIn * $xE"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:when>

    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$lenOut != 0.0">
          <xsl:value-of select="$endElev + $gradeOut * $xX + $aTwo * $xX * $xX div (2.0 * $lenOut)"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="$endElev + $gradeOut * $xX"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *** Return The Elevation Of A Point On A Circular Vert Curve *** -->
<!-- **************************************************************** -->
<xsl:template name="CircularVertCurvePointElevation">
  <xsl:param name="centreStn"/>
  <xsl:param name="centreElev"/>
  <xsl:param name="intersectElev"/>
  <xsl:param name="radius"/>
  <xsl:param name="ptStn"/>

  <xsl:variable name="dist" select="$ptStn - $centreStn"/>

  <xsl:variable name="deltaElev">
    <xsl:call-template name="Sqrt">
      <xsl:with-param name="num" select="$radius * $radius - $dist * $dist"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$intersectElev &lt; $centreElev">
      <xsl:value-of select="$centreElev - $deltaElev"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$centreElev + $deltaElev"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return Appropriate Super and Widening ************** -->
<!-- **************************************************************** -->
<xsl:template name="GetSuperWidening">
  <xsl:param name="station"/>
  <xsl:param name="superWideningAssignment"/>

  <!-- This template returns the superelevation and widening values on both the -->
  <!-- left and right interpolated for the specified station.  The returned     -->
  <!-- node set is of the form:
          <pivot>Left/Crown/Right</pivot>
          <leftSuper>number</leftSuper>
          <rightSuper>number</rightSuper>
          <leftWidening>number</leftWidening>
          <rightWidening>number</rightWidening>
  -->

  <xsl:variable name="prevSuperWidening">
    <xsl:choose>
      <xsl:when test="(count(msxsl:node-set($superWideningAssignment)/*) &gt; 0) and
                      ($station &gt;= msxsl:node-set($superWideningAssignment)/ApplySuperelevation[1]/Station)">
        <xsl:for-each select="msxsl:node-set($superWideningAssignment)/ApplySuperelevation[(Station &lt;= $station)][last()]">
          <xsl:element name="pivot" namespace="">
            <xsl:value-of select="Pivot"/>
          </xsl:element>
          <xsl:element name="station" namespace="">
            <xsl:value-of select="Station"/>
          </xsl:element>
          <xsl:element name="leftSuper" namespace="">
            <xsl:value-of select="LeftSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="leftWidening" namespace="">
            <xsl:value-of select="LeftSide/Widening"/>
          </xsl:element>
          <xsl:element name="rightSuper" namespace="">
            <xsl:value-of select="RightSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="rightWidening" namespace="">
            <xsl:value-of select="RightSide/Widening"/>
          </xsl:element>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise>
        <xsl:element name="pivot" namespace="">
          <xsl:value-of select="'Crown'"/>
        </xsl:element>
        <xsl:element name="station" namespace="">
          <xsl:value-of select="NaN"/>
        </xsl:element>
        <xsl:element name="leftSuper" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="leftWidening" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="rightSuper" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="rightWidening" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="nextSuperWidening">
    <xsl:choose>
      <xsl:when test="(count(msxsl:node-set($superWideningAssignment)/*) &gt; 0) and
                      ($station &lt;= msxsl:node-set($superWideningAssignment)/ApplySuperelevation[last()]/Station)">
        <xsl:for-each select="msxsl:node-set($superWideningAssignment)/ApplySuperelevation[(Station &gt;= $station)][1]">
          <xsl:element name="pivot" namespace="">
            <xsl:value-of select="Pivot"/>
          </xsl:element>
          <xsl:element name="station" namespace="">
            <xsl:value-of select="Station"/>
          </xsl:element>
          <xsl:element name="leftSuper" namespace="">
            <xsl:value-of select="LeftSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="leftWidening" namespace="">
            <xsl:value-of select="LeftSide/Widening"/>
          </xsl:element>
          <xsl:element name="rightSuper" namespace="">
            <xsl:value-of select="RightSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="rightWidening" namespace="">
            <xsl:value-of select="RightSide/Widening"/>
          </xsl:element>
        </xsl:for-each>
      </xsl:when>
      <xsl:when test="(count(msxsl:node-set($superWideningAssignment)/*) &gt; 0) and
                      ($station &gt; msxsl:node-set($superWideningAssignment)/ApplySuperelevation[last()]/Station)">
        <!-- We are beyond the last station in the super/widening table so grab the values for the last element in the table. -->
        <xsl:for-each select="msxsl:node-set($superWideningAssignment)/ApplySuperelevation[last()]">
          <xsl:element name="pivot" namespace="">
            <xsl:value-of select="Pivot"/>
          </xsl:element>
          <xsl:element name="station" namespace="">
            <xsl:value-of select="Station"/>
          </xsl:element>
          <xsl:element name="leftSuper" namespace="">
            <xsl:value-of select="LeftSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="leftWidening" namespace="">
            <xsl:value-of select="LeftSide/Widening"/>
          </xsl:element>
          <xsl:element name="rightSuper" namespace="">
            <xsl:value-of select="RightSide/Superelevation"/>
          </xsl:element>
          <xsl:element name="rightWidening" namespace="">
            <xsl:value-of select="RightSide/Widening"/>
          </xsl:element>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise>
        <xsl:element name="pivot" namespace="">
          <xsl:value-of select="'Crown'"/>
        </xsl:element>
        <xsl:element name="station" namespace="">
          <xsl:value-of select="NaN"/>
        </xsl:element>
        <xsl:element name="leftSuper" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="leftWidening" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="rightSuper" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
        <xsl:element name="rightWidening" namespace="">
          <xsl:value-of select="0"/>
        </xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:element name="pivot" namespace="">
    <xsl:value-of select="msxsl:node-set($prevSuperWidening)/pivot"/>
  </xsl:element>

  <xsl:element name="leftSuper" namespace="">
    <xsl:choose>  <!-- If both the previous or next station values are null return null super grade -->
      <xsl:when test="(string(number(msxsl:node-set($prevSuperWidening)/station)) = 'NaN') and
                      (string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">NaN</xsl:when>

      <xsl:when test="(string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftSuper"/>  <!-- Past the end of the super table definition - use the last super definition -->
      </xsl:when>

      <xsl:when test="msxsl:node-set($prevSuperWidening)/station = msxsl:node-set($nextSuperWidening)/station">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftSuper"/>  <!-- Same stations so directly use super value -->
      </xsl:when>

      <xsl:otherwise>  <!-- Interpolate the super value -->
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftSuper +
                              (msxsl:node-set($nextSuperWidening)/leftSuper - msxsl:node-set($prevSuperWidening)/leftSuper) *
                              ($station - msxsl:node-set($prevSuperWidening)/station) div
                              (msxsl:node-set($nextSuperWidening)/station - msxsl:node-set($prevSuperWidening)/station)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:element>

  <xsl:element name="rightSuper" namespace="">
    <xsl:choose>  <!-- If both the previous or next station values are null return null super grade -->
      <xsl:when test="(string(number(msxsl:node-set($prevSuperWidening)/station)) = 'NaN') and
                      (string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">NaN</xsl:when>

      <xsl:when test="(string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightSuper"/>  <!-- Past the end of the super table definition - use the last super definition -->
      </xsl:when>

      <xsl:when test="msxsl:node-set($prevSuperWidening)/station = msxsl:node-set($nextSuperWidening)/station">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightSuper"/>  <!-- Same stations so directly use super value -->
      </xsl:when>

      <xsl:otherwise>  <!-- Interpolate the super value -->
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightSuper +
                              (msxsl:node-set($nextSuperWidening)/rightSuper - msxsl:node-set($prevSuperWidening)/rightSuper) *
                              ($station - msxsl:node-set($prevSuperWidening)/station) div
                              (msxsl:node-set($nextSuperWidening)/station - msxsl:node-set($prevSuperWidening)/station)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:element>

  <xsl:element name="leftWidening" namespace="">
    <xsl:choose>  <!-- If either the previous or next station values are null return 0 -->
      <xsl:when test="(string(number(msxsl:node-set($prevSuperWidening)/station)) = 'NaN') or
                      (string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">0</xsl:when>

      <xsl:when test="(string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftWidening"/>  <!-- Past the end of the super table definition - use the last widening definition -->
      </xsl:when>

      <xsl:when test="msxsl:node-set($prevSuperWidening)/station = msxsl:node-set($nextSuperWidening)/station">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftWidening"/>  <!-- Same stations so directly use widening value -->
      </xsl:when>

      <xsl:otherwise>  <!-- Interpolate the super value -->
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/leftWidening +
                              (msxsl:node-set($nextSuperWidening)/leftWidening - msxsl:node-set($prevSuperWidening)/leftWidening) *
                              ($station - msxsl:node-set($prevSuperWidening)/station) div
                              (msxsl:node-set($nextSuperWidening)/station - msxsl:node-set($prevSuperWidening)/station)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:element>

  <xsl:element name="rightWidening" namespace="">
    <xsl:choose>  <!-- If either the previous or next station values are null return 0 -->
      <xsl:when test="(string(number(msxsl:node-set($prevSuperWidening)/station)) = 'NaN') or
                      (string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">0</xsl:when>

      <xsl:when test="(string(number(msxsl:node-set($nextSuperWidening)/station)) = 'NaN')">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightWidening"/>  <!-- Past the end of the super table definition - use the last widening definition -->
      </xsl:when>

      <xsl:when test="msxsl:node-set($prevSuperWidening)/station = msxsl:node-set($nextSuperWidening)/station">
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightWidening"/>  <!-- Same stations so directly use widening value -->
      </xsl:when>

      <xsl:otherwise>
        <xsl:value-of select="msxsl:node-set($prevSuperWidening)/rightWidening +
                              (msxsl:node-set($nextSuperWidening)/rightWidening - msxsl:node-set($prevSuperWidening)/rightWidening) *
                              ($station - msxsl:node-set($prevSuperWidening)/station) div
                              (msxsl:node-set($nextSuperWidening)/station - msxsl:node-set($prevSuperWidening)/station)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:element>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return Interpolated Value Based On Station *********** -->
<!-- **************************************************************** -->
<xsl:template name="InterpolatedValueByStation">
  <xsl:param name="startValue"/>
  <xsl:param name="endValue"/>
  <xsl:param name="startStn"/>
  <xsl:param name="endStn"/>
  <xsl:param name="station"/>

  <xsl:value-of select="($startValue + ($endValue - $startValue) * ($station - $startStn) div ($endStn - $startStn))"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return the Grade for an Element **************** -->
<!-- **************************************************************** -->
<xsl:template name="ElementGrade">
  <xsl:param name="templateElement"/>

  <xsl:choose>
    <xsl:when test="name(msxsl:node-set($templateElement)) = 'DistanceAndGrade'">
      <xsl:value-of select="Grade"/>
    </xsl:when>
    <xsl:otherwise> <!-- DistanceAndVerticalDistance element-->
      <xsl:choose>
        <xsl:when test="HorizontalDistance != 0.0">  <!-- Can compute the grade -->
          <xsl:value-of select="VerticalDistance div HorizontalDistance * 100.0"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="Nan"/>  <!-- Vertical element - no grade -->
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Return Superelevated Grade ****************** -->
<!-- **************************************************************** -->
<xsl:template name="SuperelevatedGrade">
  <xsl:param name="superWideningVals"/>
  <xsl:param name="template"/>
  <xsl:param name="templateElement"/>
  <xsl:param name="firstSuperedElement"/>
  <xsl:param name="widenedDist"/>
  <xsl:param name="position"/>
  <xsl:param name="applyRollover" select="'true'"/>

  <xsl:variable name="grade">
    <xsl:call-template name="ElementGrade">
      <xsl:with-param name="templateElement" select="$templateElement"/>
    </xsl:call-template>
  </xsl:variable>

  <!-- Apply any superelevation to the grade -->
  <xsl:choose>
    <xsl:when test="string(number(msxsl:node-set($superWideningVals)/super)) != 'NaN'">
      <xsl:choose>
        <xsl:when test="(msxsl:node-set($templateElement)/ApplySuperelevation = 'true') and
                        ($position = msxsl:node-set($firstSuperedElement)/position)">
          <!-- This is the first actual supered template element - Use the specified superelevation as the grade value -->
          <xsl:value-of select="msxsl:node-set($superWideningVals)/super"/>
        </xsl:when>

        <xsl:otherwise>  <!-- Must be an unsupered element or a supered element subsequent to the first supered element -->
          <xsl:choose>
            <xsl:when test="msxsl:node-set($templateElement)/ApplySuperelevation = 'true'">
              <xsl:value-of select="$grade + msxsl:node-set($firstSuperedElement)/deltaGrade"/> <!-- Apply the delta grade at the first supered element to this element -->
            </xsl:when>

            <xsl:when test="(msxsl:node-set($templateElement)/ApplyRollover = 'true') and
                            ($applyRollover = 'true')">  <!-- ApplyRollover and ApplySuperelevation can't both be true -->
              <xsl:variable name="currentPos" select="$position"/>

              <xsl:variable name="prevElementGrade">  <!-- Compute the grade used for the previous element -->
                <xsl:for-each select="msxsl:node-set($template)/*[(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">
                  <xsl:if test="position() = $currentPos - 1">  <!-- We have the previous element -->
                    <xsl:variable name="initialGrade">
                      <xsl:call-template name="ElementGrade">
                        <xsl:with-param name="templateElement" select="."/>
                      </xsl:call-template>
                    </xsl:variable>

                    <xsl:element name="initialGrade" namespace="">
                      <xsl:value-of select="$initialGrade"/>
                    </xsl:element>

                    <xsl:element name="superGrade" namespace="">
                      <xsl:choose>
                        <xsl:when test="ApplySuperelevation = 'true'">
                          <xsl:value-of select="$initialGrade + msxsl:node-set($firstSuperedElement)/deltaGrade"/> <!-- Apply the delta grade at the first supered element to this element -->
                        </xsl:when>
                        <xsl:otherwise>
                          <xsl:value-of select="$initialGrade"/>
                        </xsl:otherwise>
                      </xsl:choose>
                    </xsl:element>
                  </xsl:if>
                </xsl:for-each>
              </xsl:variable>

              <!-- Now have the grade for the previous element - carry out the rollover tests -->
              <xsl:choose>
                <xsl:when test="(msxsl:node-set($prevElementGrade)/superGrade &gt; msxsl:node-set($prevElementGrade)/initialGrade) and
                                ((msxsl:node-set($prevElementGrade)/superGrade - $grade) &gt; RolloverGrade)"> <!-- Outside super application exceeds rollover specified -->
                  <xsl:value-of select="msxsl:node-set($prevElementGrade)/superGrade - RolloverGrade"/>
                </xsl:when>
                <xsl:when test="$grade &gt; msxsl:node-set($prevElementGrade)/superGrade"> <!-- Inside super application creates steeper grade than this element's grade -->
                  <xsl:value-of select="msxsl:node-set($prevElementGrade)/superGrade"/>    <!-- Set this element to same grade as the previous element -->
                </xsl:when>
                <xsl:otherwise>
                  <xsl:value-of select="$grade"/>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:when>

            <xsl:otherwise>
              <xsl:value-of select="$grade"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:when>

    <xsl:otherwise> <!-- No superelevation value so just use existing grade -->
      <xsl:value-of select="$grade"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- * Return Centreline Elev Adj Value For Left/Right Super Pivot ** -->
<!-- **************************************************************** -->
<xsl:template name="ComputeCLElevAdj">
  <xsl:param name="station"/>
  <xsl:param name="templates"/>
  <xsl:param name="templateNames"/>
  <xsl:param name="superWideningAssignment"/>
  <xsl:param name="pivot"/>
  <xsl:param name="prev"/>
  
  <!-- Compute the centreline vertical adjustment required for left and right pivot superelevation -->
  <!-- definitions.  This is done by computing the template deltas without superelevation applied  -->
  <!-- but with any widening applied, then computing the deltas with both superelevation and       -->
  <!-- widening applied and returning the elevation difference between the sums of the elevation   -->
  <!-- deltas from each application.  The superelevation and widening values used are those that   -->
  <!-- apply at the actual station of interest.                                                    -->

  <!-- Determine the appropriate template name based on the pivot side and $prev -->
  <!-- setting (use previous or next template)                                   -->
  <xsl:variable name="templateName">
    <xsl:choose>
      <xsl:when test="($pivot = 'Left') and ($prev = 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevLeftTemplateName"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Left') and ($prev != 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextLeftTemplateName"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Right') and ($prev = 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevRightTemplateName"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Right') and ($prev != 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextRightTemplateName"/>
      </xsl:when>
    </xsl:choose>
  </xsl:variable>

  <!-- Determine the appropriate template station based on the pivot side and $prev -->
  <!-- setting (use previous or next template)                                      -->
  <xsl:variable name="templateStation">
    <xsl:choose>
      <xsl:when test="($pivot = 'Left') and ($prev = 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevLeftTemplateStation"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Left') and ($prev != 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextLeftTemplateStation"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Right') and ($prev = 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/prevRightTemplateStation"/>
      </xsl:when>

      <xsl:when test="($pivot = 'Right') and ($prev != 'true')">
        <xsl:value-of select="msxsl:node-set($templateNames)/nextRightTemplateStation"/>
      </xsl:when>
    </xsl:choose>
  </xsl:variable>

  <!-- Get a node set of the superelevation and widening values (interpolated -->
  <!-- if required) for both sides at the specified station.                  -->
  <xsl:variable name="allSuperWideningVals">
    <xsl:call-template name="GetSuperWidening">
      <xsl:with-param name="station" select="$station"/>
      <xsl:with-param name="superWideningAssignment" select="$superWideningAssignment"/>
    </xsl:call-template>
  </xsl:variable>

  <!-- Now grab the superelevation and widening details that apply to the pivot side -->
  <xsl:variable name="superWideningVals">
    <xsl:choose>
      <xsl:when test="$pivot = 'Left'">  <!-- Get the left side values -->
        <xsl:element name="super" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/leftSuper"/>
        </xsl:element>

        <xsl:element name="widening" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/leftWidening"/>
        </xsl:element>
      </xsl:when>

      <xsl:otherwise>  <!-- Get the right side values -->
        <xsl:element name="super" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/rightSuper"/>
        </xsl:element>

        <xsl:element name="widening" namespace="">
          <xsl:value-of select="msxsl:node-set($allSuperWideningVals)/rightWidening"/>
        </xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Compute the delta elevation value from the centreline to the end of the last -->
  <!-- superelevated element for the template without any superelevation applied.   -->
  <xsl:variable name="unsuperedDeltaElevs">
    <xsl:for-each select="msxsl:node-set($templates)/Template[Name = $templateName]">
      <xsl:for-each select="*[(ApplySuperelevation = 'true') or (count(following-sibling::*[ApplySuperelevation = 'true']) != 0)]
                             [(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">
        <xsl:variable name="widenedDist">  <!-- Still apply any widening if appropriate -->
          <xsl:choose>
            <xsl:when test="ApplyWidening = 'true'">
              <xsl:value-of select="HorizontalDistance + msxsl:node-set($superWideningVals)/widening"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="HorizontalDistance"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>

        <xsl:element name="deltaElev" namespace="">
          <xsl:choose>
            <xsl:when test="name(.) = 'DistanceAndGrade'">
              <xsl:value-of select="$widenedDist * Grade div 100.0"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="VerticalDistance"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:variable>

  <xsl:variable name="unsuperedDeltaElev" select="sum(msxsl:node-set($unsuperedDeltaElevs)/deltaElev)"/>

  <xsl:variable name="firstSuperedElement">
    <xsl:for-each select="msxsl:node-set($templates)/Template/*[(ApplySuperelevation = 'true') or (count(following-sibling::*[ApplySuperelevation = 'true']) != 0)]
                                                               [(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">
      <xsl:if test="(ApplySuperelevation = 'true') and (count(preceding-sibling::*[ApplySuperelevation = 'true']) = 0)">
        <!-- This element has super switched on and no preceding elements had super switched on -->
        <xsl:element name="position" namespace="">
          <xsl:value-of select="position()"/>
        </xsl:element>

        <xsl:element name="deltaGrade" namespace="">
          <xsl:variable name="origGrade">
            <xsl:call-template name="ElementGrade">
              <xsl:with-param name="templateElement" select="."/>
            </xsl:call-template>
          </xsl:variable>

          <xsl:value-of select="msxsl:node-set($superWideningVals)/super - $origGrade"/>
        </xsl:element>
      </xsl:if>
    </xsl:for-each>
  </xsl:variable>

  <!-- Now compute the delta elevation value from the centreline to the end of the  -->
  <!-- last superelevated element with the superelevation and widening applied.     -->
  <xsl:variable name="superedDeltaElevs">
    <xsl:for-each select="msxsl:node-set($templates)/Template[Name = $templateName]">
      <xsl:for-each select="*[(ApplySuperelevation = 'true') or (count(following-sibling::*[ApplySuperelevation = 'true']) != 0)]
                             [(name(.) != 'Name') and (name(.) != 'SideSlope') and (name(.) != 'Deleted')]">

        <xsl:variable name="widenedDist">
          <xsl:choose>
            <xsl:when test="ApplyWidening = 'true'">
              <xsl:value-of select="HorizontalDistance + msxsl:node-set($superWideningVals)/widening"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="HorizontalDistance"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:variable>

        <!-- Apply any superelevation to the grade -->
        <xsl:variable name="superGrade">
          <xsl:call-template name="SuperelevatedGrade">
            <xsl:with-param name="superWideningVals" select="$superWideningVals"/>
            <xsl:with-param name="template" select="parent::Template"/>
            <xsl:with-param name="templateElement" select="."/>
            <xsl:with-param name="firstSuperedElement" select="$firstSuperedElement"/>
            <xsl:with-param name="widenedDist" select="$widenedDist"/>
            <xsl:with-param name="position" select="position()"/>
            <xsl:with-param name="applyRollover" select="'false'"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:element name="deltaElev" namespace="">
          <xsl:choose>
            <xsl:when test="string(number($superGrade)) = 'NaN'">  <!-- No grade - must be vertical -->
              <xsl:value-of select="VerticalDistance"/>            <!-- Use the VerticalDistance value -->
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$widenedDist * $superGrade div 100.0"/>  <!-- Apply superelevated grade to widened horiz distance -->
            </xsl:otherwise>
          </xsl:choose>
        </xsl:element>

      </xsl:for-each>
    </xsl:for-each>
  </xsl:variable>
  
  <xsl:variable name="superedDeltaElev" select="sum(msxsl:node-set($superedDeltaElevs)/deltaElev)"/>
  
  <!-- Return the difference between the supered and unsupered delta elevation -->
  <xsl:value-of select="$unsuperedDeltaElev - $superedDeltaElev"/>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Compute Inverse Distance ******************** -->
<!-- **************************************************************** -->
<xsl:template name="InverseDistance">
  <xsl:param name="deltaN"/>
  <xsl:param name="deltaE"/>

  <!-- Compute the inverse distance from the deltas -->
  <xsl:choose>  <!-- If delta values are both effectively 0 return 0 -->
    <xsl:when test="((concat(substring('-',2 - ($deltaN &lt; 0)), '1') * $deltaN) &lt; 0.000001) and
                    ((concat(substring('-',2 - ($deltaE &lt; 0)), '1') * $deltaE) &lt; 0.000001)">0</xsl:when>
    <xsl:otherwise>
      <!-- Return hypotenuse distance -->
      <xsl:call-template name="Sqrt">
        <xsl:with-param name="num" select="$deltaN * $deltaN + $deltaE * $deltaE"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Calculate a spiral deflection angle ************** -->
<!-- **************************************************************** -->
<xsl:template name="CalcSpiralDeflection">
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>
  <xsl:param name="length"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="along"/>  <!-- Only used for KoreanCubicParabola -->
  <xsl:param name="spiralType" select="'Clothoid'"/>  <!-- Can be 'Clothoid', 'KoreanCubicParabola', 'Cubic' or 'Bloss' -->
  
  <xsl:if test="(string(number($length)) != 'NaN') and (string(number($smallRadius)) != 'NaN') and
                (string(number($spiralDist)) != 'NaN') and ($spiralDist &gt;= 0) and ($spiralDist &lt;= $length)">
    <!-- We have valid input values -->
    <xsl:choose>
      <xsl:when test="($spiralDist = 0.0) or ($smallRadius = 0.0)">
        <xsl:value-of select="0.0"/>  <!-- Return a deflection angle of 0 -->
      </xsl:when>

      <xsl:when test="string(number($largeRadius)) = 'NaN'">  <!-- Standard spiral calculation - Clothoid spiral, Cubic spiral and Cubic parabola -->
        <xsl:choose>
          <xsl:when test="($spiralType = 'Clothoid') or ($spiralType = 'Cubic')">
            <xsl:variable name="K" select="$smallRadius * $length"/>
            <xsl:value-of select="($spiralDist * $spiralDist) div (2.0 * $K) * 180.0 div $Pi"/>
          </xsl:when>

          <xsl:when test="$spiralType = 'Bloss'">  <!-- Bloss spiral -->
            <xsl:value-of select="($spiralDist * $spiralDist * $spiralDist div ($smallRadius * $length * $length) -
                                   $spiralDist * $spiralDist * $spiralDist * $spiralDist div (2.0 * $smallRadius * $length * $length * $length)) * 180.0 div $Pi"/>
          </xsl:when>
          
          <xsl:otherwise>   <!-- KoreanCubicParabola -->
            <xsl:variable name="angle">
              <xsl:call-template name="ArcTanSeries">
                <xsl:with-param name="tanVal" select="$along div (2.0 * $smallRadius)"/>
              </xsl:call-template>
            </xsl:variable>
            <xsl:value-of select="$angle * 180.0 div $Pi"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:when>

      <xsl:otherwise>
        <xsl:choose>
          <xsl:when test="$largeRadius != $smallRadius">
            <!-- No partial spiral deflection computation for KoreanCubicParabola or Bloss spiral -->
            <xsl:variable name="K" select="($smallRadius * $largeRadius * $length) div ($largeRadius - $smallRadius)"/>
            <xsl:variable name="prevLength" select="concat(substring('-',2 - (($K div $smallRadius) &lt; 0)), '1') * ($K div $smallRadius) - $length"/>
            <xsl:variable name="localDist" select="$prevLength + $spiralDist"/>
            <xsl:variable name="startDeflection" select="($prevLength * $prevLength) div (2.0 * $K)"/>
            <xsl:value-of select="(($localDist * $localDist) div (2.0 * $K) - $startDeflection) * 180.0 div $Pi"/>
          </xsl:when>

          <xsl:otherwise>   <!-- This is a special case of an arc -->
            <xsl:value-of select="($length div $smallRadius) * 180.0 div $Pi"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- *** Calculate spiral deflection angle for NSWCubicParabola ***** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWSpiralDeflection">
  <xsl:param name="smallRadius"/>
  <xsl:param name="transitionXc"/>

  <xsl:variable name="sqRoot3" select="1.73205080756887729"/>
  
  <xsl:variable name="arcCosVal">
    <xsl:call-template name="ArcCos">
      <xsl:with-param name="cosVal" select="-3.0 * $sqRoot3 * $transitionXc div (4.0 * $smallRadius)"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:variable name="arcCosValInDeg" select="$arcCosVal * (180.0 div $Pi)"/>
  
  <xsl:variable name="cosVal">
    <xsl:call-template name="Cosine">
      <xsl:with-param name="theAngle" select="($arcCosValInDeg div 3.0 + 240.0) * $Pi div 180.0"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:variable name="radiansVal">
    <xsl:call-template name="ArcSin">
      <xsl:with-param name="sinVal" select="2.0 div $sqRoot3 * $cosVal"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:value-of select="$radiansVal * 180.0 div $Pi"/>  <!-- Return deflection value in degrees -->
</xsl:template>


<!-- **************************************************************** -->
<!-- **** Calculate NSWCubicParabola radius at dist along spiral **** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWRadiusAtDistance">
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>
  <xsl:param name="length"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="transitionXc"/>

  <!-- Return a node set variable that provides: -->
  <!--   radius  -->
  <!--   along   -->
  
  <xsl:variable name="deflection">  <!-- Returned in degrees -->
    <xsl:call-template name="CalcNSWSpiralDeflection">
      <xsl:with-param name="smallRadius" select="$smallRadius"/>
      <xsl:with-param name="transitionXc" select="$transitionXc"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="spiralM">
    <xsl:variable name="tanDeflection">
      <xsl:call-template name="Tan">
        <xsl:with-param name="theAngle" select="$deflection * $Pi div 180.0"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:value-of select="$tanDeflection div (3.0 * $transitionXc * $transitionXc)"/>
  </xsl:variable>

  <xsl:variable name="spiralVals">
    <xsl:choose>
      <xsl:when test="string(number($largeRadius)) = 'NaN'"> <!-- This is a standard spiral to infinity -->
        <xsl:call-template name="CalcNSWSpiralXY">
          <xsl:with-param name="spiralDist" select="$spiralDist"/>
          <xsl:with-param name="spiralM" select="$spiralM"/>
        </xsl:call-template>
      </xsl:when>
      <xsl:otherwise>  <!-- This is a spiral between 2 arcs -->
        <xsl:variable name="totalLength">  <!-- Spiral length from infinity to smallRadius -->
          <xsl:call-template name="CalcNSWSpiralLength">
            <xsl:with-param name="transitionXc" select="$transitionXc"/>
            <xsl:with-param name="spiralM" select="$spiralM"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:variable name="lengthToPoint" select="$totalLength - ($length - $spiralDist)"/>

        <xsl:call-template name="CalcNSWSpiralXY">
          <xsl:with-param name="spiralDist" select="$lengthToPoint"/>
          <xsl:with-param name="spiralM" select="$spiralM"/>
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="x" select="msxsl:node-set($spiralVals)/along"/>
  <xsl:variable name="term" select="1.0 + 9.0 * $spiralM * $spiralM * $x * $x * $x * $x"/>
  <xsl:variable name="num">
    <xsl:call-template name="Sqrt">
      <xsl:with-param name="num" select="$term * $term * $term"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:element name="radius" namespace="">
    <xsl:value-of select="$num div (6.0 * $spiralM * $x)"/>
  </xsl:element>
  
  <xsl:element name="along" namespace="">
    <xsl:value-of select="$x"/>
  </xsl:element>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Recursive func to calc NSWCubicParabola transitionXc ***** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWIterateXcStandard">  <!-- Standard fully defined case -->
  <xsl:param name="transitionXc"/>
  <xsl:param name="length"/>
  <xsl:param name="smallRadius"/>

  <xsl:variable name="deflection">  <!-- Returned in degrees -->
    <xsl:call-template name="CalcNSWSpiralDeflection">
      <xsl:with-param name="smallRadius" select="$smallRadius"/>
      <xsl:with-param name="transitionXc" select="$transitionXc"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="spiralM">
    <xsl:variable name="tanDeflection">
      <xsl:call-template name="Tan">
        <xsl:with-param name="theAngle" select="$deflection * $Pi div 180.0"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:value-of select="$tanDeflection div (3.0 * $transitionXc * $transitionXc)"/>
  </xsl:variable>

  <!-- Get the calculated spiral length based on the current Xc value -->
  <xsl:variable name="calcLength">
    <xsl:call-template name="CalcNSWSpiralLength">
      <xsl:with-param name="transitionXc" select="$transitionXc"/>
      <xsl:with-param name="spiralM" select="$spiralM"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="absLengthDelta" select="concat(substring('-',2 - (($calcLength - $length) &lt; 0)), '1') * ($calcLength - $length)"/>

  <xsl:choose>
    <xsl:when test="$absLengthDelta &gt; 0.0000001">
      <!-- Recurse function adjusting transitionXc value by known length to computed length proportion -->
      <xsl:call-template name="CalcNSWIterateXcStandard">
        <xsl:with-param name="transitionXc" select="$transitionXc * $length div $calcLength"/>
        <xsl:with-param name="length" select="$length"/>
        <xsl:with-param name="smallRadius" select="$smallRadius"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$transitionXc"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Recursive func to calc NSWCubicParabola transitionXc ***** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWIterateXcCompound">  <!-- Compound transition between 2 arcs case -->
  <xsl:param name="transitionXc"/>
  <xsl:param name="length"/>
  <xsl:param name="smallRadius"/>
  <xsl:param name="largeRadius"/>

  <xsl:variable name="deflection">  <!-- Returned in degrees -->
    <xsl:call-template name="CalcNSWSpiralDeflection">
      <xsl:with-param name="smallRadius" select="$smallRadius"/>
      <xsl:with-param name="transitionXc" select="$transitionXc"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="spiralM">
    <xsl:variable name="tanDeflection">
      <xsl:call-template name="Tan">
        <xsl:with-param name="theAngle" select="$deflection * $Pi div 180.0"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:value-of select="$tanDeflection div (3.0 * $transitionXc * $transitionXc)"/>
  </xsl:variable>

  <xsl:variable name="transitionXl">
    <xsl:call-template name="CalcNSWIterateXl">
      <xsl:with-param name="transitionXl" select="1.0 div (6.0 * $spiralM * $largeRadius)"/>
      <xsl:with-param name="largeRadius" select="$largeRadius"/>
      <xsl:with-param name="spiralM" select="$spiralM"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="lenLargeRad">
    <xsl:call-template name="CalcNSWSpiralLength">
      <xsl:with-param name="transitionXc" select="$transitionXl"/>
      <xsl:with-param name="spiralM" select="$spiralM"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="totalLength">
    <xsl:call-template name="CalcNSWSpiralLength">
      <xsl:with-param name="transitionXc" select="$transitionXc"/>
      <xsl:with-param name="spiralM" select="$spiralM"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:variable name="absLengthDelta" select="concat(substring('-',2 - ((($totalLength - $lenLargeRad) - $length) &lt; 0)), '1') * (($totalLength - $lenLargeRad) - $length)"/>

  <xsl:choose>
    <xsl:when test="$absLengthDelta &gt; 0.0000001">
      <!-- Recurse function adjusting transitionXc value by known length to computed length proportion -->
      <xsl:call-template name="CalcNSWIterateXcCompound">
        <xsl:with-param name="transitionXc" select="$transitionXc * $length div ($totalLength - $lenLargeRad)"/>
        <xsl:with-param name="length" select="$length"/>
        <xsl:with-param name="smallRadius" select="$smallRadius"/>
        <xsl:with-param name="largeRadius" select="$largeRadius"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$transitionXc"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Calculate spiral X and Y values *************** -->
<!-- **************************************************************** -->
<xsl:template name="CalcSpiralXY">
  <xsl:param name="spiralDist"/>
  <xsl:param name="K"/>           <!-- Used for Clothoid spiral, Cubic spiral and KoreanCubicParabola transitions -->
  <xsl:param name="spiralM"/>     <!-- Used for NSWCubicParabola transition -->
  <xsl:param name="spiralType"/>
  <xsl:param name="smallRadius"/> <!-- Used for Bloss spiral transition -->
  <xsl:param name="length"/>      <!-- Used for Bloss spiral transition -->

  <!-- Returns node-set variable with the elements:  -->
  <!--   along                                       -->
  <!--   across                                      -->

  <xsl:variable name="squaredDist" select="$spiralDist * $spiralDist"/>
  <xsl:variable name="t1" select="($squaredDist div (2.0 * $K)) * ($squaredDist div (2.0 * $K)) * -1.0"/>

  <xsl:choose>
    <xsl:when test="($spiralType = 'Clothoid') or ($spiralType = 'KoreanCubicParabola') or ($spiralType = 'Cubic')"> <!-- Clothoid spiral, KoreanCubicParabola or Cubic spiral -->
      <!-- Calculate displacement along entry azimuth -->
      <!-- Computation of displacement along the entry azimuth is identical for Clothoid spiral, KoreanCubicParabola and Cubic spiral -->
      <xsl:variable name="alongTerm" select="$spiralDist"/>

      <xsl:variable name="along">
        <xsl:call-template name="alongTermIter">
          <xsl:with-param name="count" select="1"/>
          <xsl:with-param name="t1" select="$t1"/>
          <xsl:with-param name="alongTerm" select="$alongTerm"/>
          <xsl:with-param name="along" select="$alongTerm"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:element name="along" namespace="">
        <xsl:value-of select="$along"/>
      </xsl:element>

      <!-- Calculate displacement normal to entry azimuth -->
      <xsl:element name="across" namespace="">
        <xsl:choose>
          <xsl:when test="$spiralType = 'Clothoid'">  <!-- Clothoid spiral -->
            <xsl:variable name="acrossTerm" select="$squaredDist * $spiralDist div (6.0 * $K)"/>

            <xsl:call-template name="acrossTermIter">
              <xsl:with-param name="count" select="1"/>
              <xsl:with-param name="t1" select="$t1"/>
              <xsl:with-param name="acrossTerm" select="$acrossTerm"/>
              <xsl:with-param name="across" select="$acrossTerm"/>
            </xsl:call-template>
          </xsl:when>

          <xsl:when test="$spiralType = 'Cubic'">
            <xsl:value-of select="$squaredDist * $spiralDist div (6.0 * $K)"/>
          </xsl:when>

          <xsl:otherwise>  <!-- KoreanCubicParabola transition -->
            <xsl:value-of select="$along * $along div (6.0 * $K div $spiralDist)"/>  <!-- No iteration required -->
          </xsl:otherwise>
        </xsl:choose>
      </xsl:element>
    </xsl:when>

    <xsl:when test="$spiralType = 'NSWCubicParabola'">  <!-- NSWCubicParabola type transition -->
      <xsl:call-template name="CalcNSWSpiralXY">
        <xsl:with-param name="spiralDist" select="$spiralDist"/>
        <xsl:with-param name="spiralM" select="$spiralM"/>
      </xsl:call-template>
    </xsl:when>
    
    <xsl:when test="$spiralType = 'Bloss'">
      <xsl:call-template name="CalcBlossSpiralXY">
        <xsl:with-param name="spiralDist" select="$spiralDist"/>
        <xsl:with-param name="smallRadius" select="$smallRadius"/>
        <xsl:with-param name="length" select="$length"/>
      </xsl:call-template>
    </xsl:when>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Calculate spiral X and Y values for NSWCubicParabola ***** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWSpiralXY">
  <xsl:param name="spiralDist"/>
  <xsl:param name="spiralM"/>

  <!-- Returns node-set variable with the elements:  -->
  <!--   along                                       -->
  <!--   across                                      -->

  <xsl:variable name="squaredDist" select="$spiralDist * $spiralDist"/>
  <xsl:variable name="t1" select="($spiralM * $squaredDist) * ($spiralM * $squaredDist) * -1"/>

  <xsl:variable name="along">
    <xsl:call-template name="alongNSWTermIter">
      <xsl:with-param name="count" select="1"/>
      <xsl:with-param name="t1" select="$t1"/>
      <xsl:with-param name="t1Start" select="$t1"/>
      <xsl:with-param name="spiralDist" select="$spiralDist"/>
      <xsl:with-param name="alongTerm" select="$spiralDist"/>
      <xsl:with-param name="along" select="$spiralDist"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:element name="along" namespace="">
    <xsl:value-of select="$along"/>
  </xsl:element>
  
  <xsl:element name="across" namespace="">
    <xsl:value-of select="$spiralM * $along * $along * $along"/>
  </xsl:element>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Calculate NSWCubicParabola spiral length ************ -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWSpiralLength">
  <xsl:param name="transitionXc"/>
  <xsl:param name="spiralM"/>

  <xsl:variable name="squaredDist" select="$transitionXc * $transitionXc"/>
  <xsl:variable name="t1" select="($spiralM * $squaredDist) * ($spiralM * $squaredDist)"/>

  <xsl:call-template name="lengthNSWTermIter">
    <xsl:with-param name="count" select="1"/>
    <xsl:with-param name="t1" select="$t1"/>
    <xsl:with-param name="t1Start" select="$t1 * -1"/>
    <xsl:with-param name="transitionXc" select="$transitionXc"/>
    <xsl:with-param name="lengthTerm" select="$transitionXc"/>
    <xsl:with-param name="length" select="$transitionXc"/>
  </xsl:call-template>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return radians angle between Specified Limits ******** -->
<!-- **************************************************************** -->
<xsl:template name="RadianAngleBetweenLimits">
  <xsl:param name="anAngle"/>
  <xsl:param name="minVal" select="0.0"/>
  <xsl:param name="maxVal" select="$Pi * 2.0"/>
  <xsl:param name="incVal" select="$Pi * 2.0"/>

  <xsl:variable name="angle1">
    <xsl:call-template name="AngleValueLessThanMax">
      <xsl:with-param name="inAngle" select="$anAngle"/>
      <xsl:with-param name="maxVal" select="$maxVal"/>
      <xsl:with-param name="incVal" select="$incVal"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="angle2">
    <xsl:call-template name="AngleValueGreaterThanMin">
      <xsl:with-param name="inAngle" select="$angle1"/>
      <xsl:with-param name="minVal" select="$minVal"/>
      <xsl:with-param name="incVal" select="$incVal"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="$angle2"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Return the Tangent of an angle in radians ********** -->
<!-- **************************************************************** -->
<xsl:template name="Tan">
  <xsl:param name="theAngle"/>
  <xsl:param name="prec" select="0.00000001"/>
  <xsl:param name="abortIfInvalid" select="1"/>

  <xsl:variable name="xDivHalfPi" select="floor($theAngle div $halfPi)"/>
  <xsl:variable name="xHalfPiDiff" select="$theAngle - $halfPi * $xDivHalfPi"/>

  <xsl:choose>  <!-- Check for a solution -->
    <xsl:when test="(-$prec &lt; $xHalfPiDiff) and
                    ($xHalfPiDiff &lt; $prec) and
                    ($xDivHalfPi mod 2 = 1)">
      <xsl:choose>
        <xsl:when test="$abortIfInvalid">
          <xsl:message terminate="yes">
            <xsl:value-of select="concat('Function error: tan() not defined for TheAngle =', $theAngle)"/>
          </xsl:message>
        </xsl:when>

        <xsl:otherwise>Infinity</xsl:otherwise>
      </xsl:choose>
    </xsl:when>

    <!-- Compute the sine and cosine of the angle to get the tangent value -->
    <xsl:otherwise>
      <xsl:variable name="vSin">
        <xsl:call-template name="Sine">
          <xsl:with-param name="theAngle" select="$theAngle"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:variable name="vCos">
        <xsl:call-template name="Cosine">
          <xsl:with-param name="theAngle" select="$theAngle"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:value-of select="$vSin div $vCos"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******* Return the arcTan value using a series expansion ******* -->
<!-- **************************************************************** -->
<xsl:template name="ArcTanSeries">
  <xsl:param name="tanVal"/>

  <!-- If the absolute value of tanVal is greater than 1 the work with the -->
  <!-- reciprocal value and return the resultant angle subtracted from Pi. -->
  <xsl:variable name="absTanVal" select="concat(substring('-',2 - ($tanVal &lt; 0)), '1') * $tanVal"/>
  <xsl:variable name="tanVal2">
    <xsl:choose>
      <xsl:when test="$absTanVal &gt; 1.0">
        <xsl:value-of select="1.0 div $tanVal"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$tanVal"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="valSq" select="$tanVal2 * $tanVal2"/>

  <xsl:variable name="angVal">
    <xsl:value-of select="$tanVal2 div (1 + ($valSq
                                   div (3 + (4 * $valSq
                                   div (5 + (9 * $valSq
                                   div (7 + (16 * $valSq
                                   div (9 + (25 * $valSq
                                   div (11 + (36 * $valSq
                                   div (13 + (49 * $valSq
                                   div (15 + (64 * $valSq
                                   div (17 + (81 * $valSq
                                   div (19 + (100 * $valSq
                                   div (21 + (121 * $valSq
                                   div (23 + (144 * $valSq
                                   div (25 + (169 * $valSq
                                   div (27 + (196 * $valSq
                                   div (29 + (225 * $valSq))))))))))))))))))))))))))))))"/>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$absTanVal &gt; 1.0">
      <xsl:choose>
        <xsl:when test="$tanVal &lt; 0">
          <xsl:value-of select="-$halfPi - $angVal"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="$halfPi - $angVal"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$angVal"/>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return the square root of a value ************** -->
<!-- **************************************************************** -->
<xsl:template name="Sqrt">
  <xsl:param name="num" select="0"/>       <!-- The number you want to find the square root of -->
  <xsl:param name="try" select="1"/>       <!-- The current 'try'.  This is used internally. -->
  <xsl:param name="iter" select="1"/>      <!-- The current iteration, checked against maxiter to limit loop count - used internally -->
  <xsl:param name="maxiter" select="40"/>  <!-- Set this up to insure against infinite loops - used internally -->

  <!-- This template uses Sir Isaac Newton's method of finding roots -->

  <xsl:choose>
    <xsl:when test="$num &lt; 0"></xsl:when>  <!-- Invalid input - no square root of a negative number so return null -->
    <xsl:when test="$try * $try = $num or $iter &gt; $maxiter">
      <xsl:value-of select="$try"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="Sqrt">
        <xsl:with-param name="num" select="$num"/>
        <xsl:with-param name="try" select="$try - (($try * $try - $num) div (2 * $try))"/>
        <xsl:with-param name="iter" select="$iter + 1"/>
        <xsl:with-param name="maxiter" select="$maxiter"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***** Recursive func to calc NSWCubicParabola transitionXl ***** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWIterateXl">
  <xsl:param name="transitionXl"/>
  <xsl:param name="largeRadius"/>
  <xsl:param name="spiralM"/>

  <xsl:variable name="calcLargeRadius">
    <xsl:call-template name="CalcNSWRadiusAtTangentDistance">
      <xsl:with-param name="transitionXc" select="$transitionXl"/>
      <xsl:with-param name="spiralM" select="$spiralM"/>
    </xsl:call-template>
  </xsl:variable>
  
  <xsl:variable name="absRadDelta" select="concat(substring('-',2 - (($calcLargeRadius - $largeRadius) &lt; 0)), '1') * ($calcLargeRadius - $largeRadius)"/>

  <xsl:choose>
    <xsl:when test="$absRadDelta &gt; 0.0000001">
      <!-- Recurse function adjusting transitionXl value by computed large radius to known large radius proportion -->
      <xsl:call-template name="CalcNSWIterateXl">
        <xsl:with-param name="transitionXl" select="$transitionXl * $calcLargeRadius div $largeRadius"/>
        <xsl:with-param name="largeRadius" select="$largeRadius"/>
        <xsl:with-param name="spiralM" select="$spiralM"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$transitionXl"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<xsl:template name="acrossTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="30"/>
  <xsl:param name="t1"/>
  <xsl:param name="acrossTerm"/>
  <xsl:param name="across"/>

  <xsl:variable name="resolution" select="0.0000001"/>

  <xsl:choose>
    <xsl:when test="((concat(substring('-',2 - ($acrossTerm &lt; 0)), '1') * $acrossTerm) &gt; $resolution) and
                    ($count &lt; $maxIter)">
      <xsl:variable name="t2" select="((4 * $count + 3) * $count * (4 * $count + 2))"/>
      <xsl:variable name="term" select="$acrossTerm * ($t1 * ((4 * $count - 1) div $t2))"/>
      <!-- Now recurse function -->
      <xsl:call-template name="acrossTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1"/>
        <xsl:with-param name="acrossTerm" select="$term"/>
        <xsl:with-param name="across" select="$across + $term"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$across"/>  <!-- Return the iterated across value -->
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<xsl:template name="alongTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="30"/>
  <xsl:param name="t1"/>
  <xsl:param name="alongTerm"/>
  <xsl:param name="along"/>

  <xsl:variable name="resolution" select="0.0000001"/>

  <xsl:choose>
    <xsl:when test="((concat(substring('-',2 - ($alongTerm &lt; 0)), '1') * $alongTerm) &gt; $resolution) and
                    ($count &lt; $maxIter)">
      <xsl:variable name="t2" select="((4 * $count + 1) * $count * (4 * $count - 2))"/>
      <xsl:variable name="term" select="$alongTerm * ($t1 * ((4 * $count - 3) div $t2))"/>
      <!-- Now recurse function -->
      <xsl:call-template name="alongTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1"/>
        <xsl:with-param name="alongTerm" select="$term"/>
        <xsl:with-param name="along" select="$along + $term"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$along"/>  <!-- Return the iterated along value -->
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<xsl:template name="alongNSWTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="5"/>
  <xsl:param name="t1"/>
  <xsl:param name="t1Start"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="alongTerm"/>
  <xsl:param name="along"/>

  <xsl:variable name="resolution" select="0.0000001"/>

  <xsl:choose>
    <xsl:when test="((concat(substring('-',2 - ($alongTerm &lt; 0)), '1') * $alongTerm) &gt; $resolution) and
                    ($count &lt; $maxIter)">
      <xsl:variable name="t2">
        <xsl:choose>
          <xsl:when test="$count = 1">0.9</xsl:when>
          <xsl:when test="$count = 2">5.175</xsl:when>
          <xsl:when test="$count = 3">43.1948</xsl:when>
          <xsl:when test="$count = 4">426.0564</xsl:when>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="term" select="$t1 * $t2 * $spiralDist"/>

      <!-- Now recurse function -->
      <xsl:call-template name="alongNSWTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1 * $t1Start"/>
        <xsl:with-param name="t1Start" select="$t1Start"/>
        <xsl:with-param name="spiralDist" select="$spiralDist"/>
        <xsl:with-param name="alongTerm" select="$term"/>
        <xsl:with-param name="along" select="$along + $term"/>
      </xsl:call-template>
    </xsl:when>
    
    <xsl:otherwise>
      <xsl:value-of select="$along"/>  <!-- Return the iterated along value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<xsl:template name="lengthNSWTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="5"/>
  <xsl:param name="t1"/>
  <xsl:param name="t1Start"/>
  <xsl:param name="transitionXc"/>
  <xsl:param name="lengthTerm"/>
  <xsl:param name="length"/>

  <xsl:variable name="resolution" select="0.0000001"/>

  <xsl:choose>
    <xsl:when test="((concat(substring('-',2 - ($lengthTerm &lt; 0)), '1') * $lengthTerm) &gt; $resolution) and
                    ($count &lt; $maxIter)">
      <xsl:variable name="t2">
        <xsl:choose>
          <xsl:when test="$count = 1">0.9</xsl:when>
          <xsl:when test="$count = 2">1.125</xsl:when>   <!-- 9.0 / 8.0 -->
          <xsl:when test="$count = 3"><xsl:value-of select="729.0 div 208.0"/></xsl:when>
          <xsl:when test="$count = 4"><xsl:value-of select="32805.0 div 2176.0"/></xsl:when>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="term" select="$t1 * $t2 * $transitionXc"/>

      <!-- Now recurse function -->
      <xsl:call-template name="lengthNSWTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1 * $t1Start"/>
        <xsl:with-param name="t1Start" select="$t1Start"/>
        <xsl:with-param name="transitionXc" select="$transitionXc"/>
        <xsl:with-param name="lengthTerm" select="$term"/>
        <xsl:with-param name="length" select="$length + $term"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$length"/>  <!-- Return the iterated length value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******* Calculate spiral X and Y values for Bloss spiral ******* -->
<!-- **************************************************************** -->
<xsl:template name="CalcBlossSpiralXY">
  <xsl:param name="spiralDist"/>     <!-- Distance along spiral -->
  <xsl:param name="smallRadius"/>
  <xsl:param name="length"/>         <!-- Total length of spiral -->

  <!-- Returns node-set variable with the elements:  -->
  <!--   along                                       -->
  <!--   across                                      -->

  <xsl:variable name="t1" select="$spiralDist * $spiralDist * $spiralDist div ($smallRadius * $length * $length)"/>
  <xsl:variable name="t2" select="$t1 * $spiralDist div $length"/>
  
  <xsl:element name="along" namespace="">
    <xsl:call-template name="alongBlossTermIter">
      <xsl:with-param name="count">1</xsl:with-param>
      <xsl:with-param name="t1" select="$t1"/>
      <xsl:with-param name="t2" select="$t2"/>
      <xsl:with-param name="spiralDist" select="$spiralDist"/>
      <xsl:with-param name="along">0.0</xsl:with-param>
    </xsl:call-template>
  </xsl:element>

  <xsl:element name="across" namespace="">
    <xsl:call-template name="acrossBlossTermIter">
      <xsl:with-param name="count">1</xsl:with-param>
      <xsl:with-param name="t1" select="$t1"/>
      <xsl:with-param name="t2" select="$t2"/>
      <xsl:with-param name="spiralDist" select="$spiralDist"/>
      <xsl:with-param name="across">0.0</xsl:with-param>
    </xsl:call-template>
  </xsl:element>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******* Return radians angle less than Specificed Maximum ****** -->
<!-- **************************************************************** -->
<xsl:template name="AngleValueLessThanMax">
  <xsl:param name="inAngle"/>
  <xsl:param name="maxVal"/>
  <xsl:param name="incVal"/>

  <xsl:choose>
    <xsl:when test="$inAngle &gt; $maxVal">
      <xsl:variable name="newAngle">
        <xsl:value-of select="$inAngle - $incVal"/>
      </xsl:variable>
      <xsl:call-template name="AngleValueLessThanMax">
        <xsl:with-param name="inAngle" select="$newAngle"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$inAngle"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************* Return radians angle greater than Zero *********** -->
<!-- **************************************************************** -->
<xsl:template name="AngleValueGreaterThanMin">
  <xsl:param name="inAngle"/>
  <xsl:param name="minVal"/>
  <xsl:param name="incVal"/>

  <xsl:choose>
    <xsl:when test="$inAngle &lt; $minVal">
      <xsl:variable name="newAngle">
        <xsl:value-of select="$inAngle + $incVal"/>
      </xsl:variable>
      <xsl:call-template name="AngleValueGreaterThanMin">
        <xsl:with-param name="inAngle" select="$newAngle"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$inAngle"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Compute ArcCosine value using an expansion ********** -->
<!-- **************************************************************** -->
<xsl:template name="ArcCos">
  <xsl:param name="cosVal"/>

  <xsl:choose>
    <xsl:when test="($cosVal &gt;= -1.0) and ($cosVal &lt;= 1.0)">  <!-- We can compute a solution -->
      <!-- Use the ArcSin expansion to return the ArcCos value -->
      <xsl:variable name="arcSineVal">
        <xsl:call-template name="ArcSin">
          <xsl:with-param name="sinVal" select="$cosVal"/>       
        </xsl:call-template>
      </xsl:variable>
      <xsl:value-of select="$halfPi - $arcSineVal"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="''"/>  <!-- Return null value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *********** Compute ArcSine value using an expansion *********** -->
<!-- **************************************************************** -->
<xsl:template name="ArcSin">
  <xsl:param name="sinVal"/>
  
  <xsl:choose>
    <xsl:when test="($sinVal &gt;= -1.0) and ($sinVal &lt;= 1.0)">  <!-- We can compute a solution -->
      <xsl:variable name="valToPowerOf3" select="$sinVal * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf5" select="$valToPowerOf3 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf7" select="$valToPowerOf5 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf9" select="$valToPowerOf7 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf11" select="$valToPowerOf9 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf13" select="$valToPowerOf11 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf15" select="$valToPowerOf13 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf17" select="$valToPowerOf15 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf19" select="$valToPowerOf17 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf21" select="$valToPowerOf19 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf23" select="$valToPowerOf21 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf25" select="$valToPowerOf23 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf27" select="$valToPowerOf25 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf29" select="$valToPowerOf27 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf31" select="$valToPowerOf29 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf33" select="$valToPowerOf31 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf35" select="$valToPowerOf33 * $sinVal * $sinVal"/>
      <xsl:variable name="valToPowerOf37" select="$valToPowerOf35 * $sinVal * $sinVal"/>

      <xsl:value-of select="$sinVal + $valToPowerOf3 div 6.0
                                    + 3.0          * $valToPowerOf5  div 40.0
                                    + 5.0          * $valToPowerOf7  div 112.0
                                    + 35.0         * $valToPowerOf9  div 1152.0
                                    + 63.0         * $valToPowerOf11 div 2816
                                    + 231.0        * $valToPowerOf13 div 13312
                                    + 143.0        * $valToPowerOf15 div 10240
                                    + 6435.0       * $valToPowerOf17 div 557056.0
                                    + 12155.0      * $valToPowerOf19 div 1245184.0
                                    + 46189.0      * $valToPowerOf21 div 5505024.0
                                    + 88179.0      * $valToPowerOf23 div 12058624.0
                                    + 676039.0     * $valToPowerOf25 div 104857600.0
                                    + 1300075.0    * $valToPowerOf27 div 226492416.0
                                    + 5014575.0    * $valToPowerOf29 div 973078528.0
                                    + 9694845.0    * $valToPowerOf31 div 2080374784.0
                                    + 100180065.0  * $valToPowerOf33 div 23622320128.0
                                    + 116680311.0  * $valToPowerOf35 div 30064771072.0
                                    + 2268783825.0 * $valToPowerOf37 div 635655159808.0"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="''"/>  <!-- Return null value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- **** Calculate NSWCubicParabola radius at dist along tangent *** -->
<!-- **************************************************************** -->
<xsl:template name="CalcNSWRadiusAtTangentDistance">
  <xsl:param name="transitionXc"/>
  <xsl:param name="spiralM"/>
  
  <xsl:variable name="param1" select="1.0 + 9.0 * $spiralM * $spiralM * $transitionXc * $transitionXc * $transitionXc * $transitionXc"/>
  <!-- Variable numerator is param1 to power of 3/2 (square root of cube of value) -->
  <xsl:variable name="numerator">
    <xsl:call-template name="Sqrt">
      <xsl:with-param name="num" select="$param1 * $param1 * $param1"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="$numerator div (6.0 * $spiralM * $transitionXc)"/>
</xsl:template>


<xsl:template name="alongBlossTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="3"/>
  <xsl:param name="t1"/>
  <xsl:param name="t2"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="along"/>

  <xsl:choose>
    <xsl:when test="$count &lt;= $maxIter">
      <xsl:variable name="t3">
        <xsl:choose>
          <xsl:when test="$count = 1">1.0</xsl:when>
          <xsl:when test="$count = 2">
            <xsl:value-of select="- $t1 * $t1 div 14.0 +
                                    $t1 * $t2 div 16.0 -
                                    $t2 * $t2 div 72.0"/>
          </xsl:when>
          <xsl:when test="$count = 3">
            <xsl:value-of select="$t1 * $t1 * $t1 * $t1 div 312.0 -
                                  $t1 * $t1 * $t1 * $t2 div 168.0 +
                                  $t1 * $t1 * $t2 * $t2 div 240.0 -
                                  $t1 * $t2 * $t2 * $t2 div 768.0 +
                                  $t2 * $t2 * $t2 * $t2 div 6528.0"/>
          </xsl:when>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="term" select="$spiralDist * $t3"/>

      <!-- Now recurse function -->
      <xsl:call-template name="alongBlossTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1"/>
        <xsl:with-param name="t2" select="$t2"/>
        <xsl:with-param name="spiralDist" select="$spiralDist"/>
        <xsl:with-param name="along" select="$along + $term"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$along"/>  <!-- Return the iterated along value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<xsl:template name="acrossBlossTermIter">
  <xsl:param name="count"/>
  <xsl:param name="maxIter" select="2"/>
  <xsl:param name="t1"/>
  <xsl:param name="t2"/>
  <xsl:param name="spiralDist"/>
  <xsl:param name="across"/>

  <xsl:choose>
    <xsl:when test="$count &lt;= $maxIter">
      <xsl:variable name="t3">
        <xsl:choose>
          <xsl:when test="$count = 1">
            <xsl:value-of select="$t1 div 4.0 - $t2 div 10.0"/>
          </xsl:when>
          <xsl:when test="$count = 2">
            <xsl:value-of select="- $t1 * $t1 * $t1 div 60.0 +
                                    $t1 * $t1 * $t2 div 44.0 -
                                    $t1 * $t2 * $t2 div 96.0 +
                                    $t2 * $t2 * $t2 div 624.0"/>
          </xsl:when>
        </xsl:choose>
      </xsl:variable>

      <xsl:variable name="term" select="$spiralDist * $t3"/>

      <!-- Now recurse function -->
      <xsl:call-template name="acrossBlossTermIter">
        <xsl:with-param name="count" select="$count + 1"/>
        <xsl:with-param name="maxIter" select="$maxIter"/>
        <xsl:with-param name="t1" select="$t1"/>
        <xsl:with-param name="t2" select="$t2"/>
        <xsl:with-param name="spiralDist" select="$spiralDist"/>
        <xsl:with-param name="across" select="$across + $term"/>
      </xsl:call-template>
    </xsl:when>

    <xsl:otherwise>
      <xsl:value-of select="$across"/>  <!-- Return the iterated across value -->
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


</xsl:stylesheet>
