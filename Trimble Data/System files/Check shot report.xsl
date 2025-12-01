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

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

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

<xsl:variable name="userField1" select="'checkType|Report on|stringMenu|2|All conventional check shots|Backsight check shots only'"/>
<xsl:variable name="checkType" select="'All conventional check shots'"/>
<xsl:variable name="userField2" select="'hzTolForHighlight|Horizontal delta tolerance|double|0.0|1.0'"/>
<xsl:variable name="hzTolForHighlight" select="0.010"/>
<xsl:variable name="userField3" select="'vtTolForHighlight|Vertical delta tolerance|double|0.0|1.0'"/>
<xsl:variable name="vtTolForHighlight" select="0.010"/>

<xsl:key name="bsID-search" match="/JOBFile/FieldBook/BackBearingRecord" use="@ID"/>
<xsl:key name="stnID-search" match="/JOBFile/FieldBook/StationRecord" use="@ID"/>
<xsl:key name="ptFromStn-search" match="/JOBFile/FieldBook/PointRecord" use="StationID"/>

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
    <xsl:when test="$DistUnit = 'Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit = 'InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit = 'USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit = 'DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit = 'Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit = 'Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder = 'North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder = 'X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit = 'MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit = 'InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit = 'mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="product">
  <xsl:choose>
    <xsl:when test="JOBFile/@product"><xsl:value-of select="JOBFile/@product"/></xsl:when>
    <xsl:otherwise>Trimble Survey Controller</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="version">
  <xsl:choose>
    <xsl:when test="JOBFile/@productVersion"><xsl:value-of select="JOBFile/@productVersion"/></xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>

  <title>Check Shot Report</title>
  <h2>Check Shot Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    html { font-family: Arial }
    body, table, td, th
    {
      font-size:13px;
    }
    th.blackTitleLine {background-color: black; color: white}
    th.silverTitleLine {background-color: silver}
    td.highlightRed {color: red; font: bold}
    td.bold {font: bold}
  </style>

  <head>
  </head>

  <body>
  <table border="0" width="60%" cellpadding="5">
    <tr>
      <th align="left">Job name:</th>
      <td><xsl:value-of select="JOBFile/@jobName"/></td>
    </tr>
    <tr>
      <th align="left"><xsl:value-of select="$product"/> version:</th>
      <td><xsl:value-of select="$version"/></td>
    </tr>
    <xsl:if test="JOBFile/@TimeStamp != ''"> <!-- Date could be null in an updated job -->
      <tr>
        <th align="left">Creation date:</th>
        <td><xsl:value-of select="substring-before(JOBFile/@TimeStamp, 'T')"/></td>
      </tr>
    </xsl:if>
    <tr>
      <th align="left">Distance/Coord units:</th>
      <td>
        <xsl:choose>
          <xsl:when test="$DistUnit = 'Metres'">Meters</xsl:when>
          <xsl:when test="$DistUnit = 'InternationalFeet'">International Feet</xsl:when>
          <xsl:when test="$DistUnit = 'USSurveyFeet'">US Survey Feet</xsl:when>
          <xsl:otherwise>Meters</xsl:otherwise>
        </xsl:choose>
      </td>
    </tr>
    <tr>
      <th align="left">Angle units:</th>
      <td>
        <xsl:choose>
          <xsl:when test="$AngleUnit = 'DMSDegrees'">DMS Degrees</xsl:when>
          <xsl:when test="$AngleUnit = 'Gons'">Gons</xsl:when>
          <xsl:when test="$AngleUnit = 'Mils'">Mils</xsl:when>
          <xsl:otherwise>Decimal Degrees</xsl:otherwise>
        </xsl:choose>
      </td>
    </tr>
    <tr>
      <th align="left">Reporting on:</th>
      <td><xsl:value-of select="$checkType"/></td>
    </tr>
  </table>
  
  <xsl:call-template name="SeparatingLine"/>
  <xsl:value-of select="concat('Highlighted shots exceed the horizontal (', $hzTolForHighlight, ') or vertical (', $vtTolForHighlight, ') delta tolerances.')"/>
  <xsl:call-template name="SeparatingLine"/>

  <!-- Output any conventional check shots first -->
  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (Classification = 'Check') and Circle]) != 0">
    <table border="1" width="100%" cellpadding="5">
      <caption align="top"><p align="left"><b>Deltas for Conventional Check Shots</b></p></caption>
      <tr>
        <th class="silverTitleLine" width="24%">Station</th>
        <th class="silverTitleLine" width="24%">Point</th>
        <th class="silverTitleLine" width="22%">dHz Obs</th>
        <th class="silverTitleLine" width="15%">dHoriz</th>
        <th class="silverTitleLine" width="15%">dVert</th>
      </tr>

      <!-- Process the undeleted PointRecord elements in the FieldBook node -->
      <!-- that have the Check classification and a Circle element          -->
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (Classification = 'Check') and Circle]" mode="Conventional"/>

    </table>
  </xsl:if>

  <br/>
  
  <!-- Output any GNSS check shots -->
  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (Classification = 'Check') and ObservationPolarDeltas and (ECEFDeltas or ECEF)]) != 0">
    <table border="1" width="100%" cellpadding="5">
      <caption align="top"><p align="left"><b>Deltas for GNSS Check Shots</b></p></caption>
      <tr>
        <th class="silverTitleLine" width="40%">Point</th>
        <th class="silverTitleLine" width="30%">dHoriz</th>
        <th class="silverTitleLine" width="30%">dVert</th>
      </tr>

      <!-- Process the undeleted PointRecord elements in the FieldBook node -->
      <!-- that have the Check classification and a Circle element          -->
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (Classification = 'Check') and ObservationPolarDeltas and (ECEFDeltas or ECEF)]" mode="GNSS"/>

    </table>
  </xsl:if>
  </body>
  </html>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Conventional PointRecord Output *************** -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="Conventional">

  <xsl:variable name="nameStr" select="Name"/>

  <xsl:variable name="bsID" select="BackBearingID"/>
  <xsl:variable name="bsStr">
    <xsl:for-each select="key('bsID-search', BackBearingID)">
      <xsl:choose>
        <xsl:when test="$nameStr = BackSight"> (BS)</xsl:when>
        <xsl:otherwise></xsl:otherwise>
      </xsl:choose>
    </xsl:for-each>
  </xsl:variable>

  <xsl:variable name="face" select="Circle/Face"/>

  <!-- Get then backsight hz observation if a backsight check -->
  <xsl:variable name="bsObs">
    <xsl:if test="$bsStr != ''">
      <xsl:for-each select="key('bsID-search', BackBearingID)">
        <xsl:if test="($face = 'Face1') or ($face = 'FaceNull')">
          <xsl:value-of select="Face1HorizontalCircle"/>
        </xsl:if>
        <xsl:if test="$face = 'Face2'">
          <xsl:value-of select="Face2HorizontalCircle"/>
        </xsl:if>
      </xsl:for-each>
    </xsl:if>
  </xsl:variable>

  <xsl:variable name="deltaAngle">
    <xsl:choose>
      <xsl:when test="($bsStr != '') and (string(number($bsObs)) != 'NaN')">  <!-- This is a backsight check and we have a backsight hz obs -->
        <xsl:value-of select="$bsObs - Circle/HorizontalCircle"/>  <!-- Report delta from current obs to BS -->
      </xsl:when>

      <xsl:otherwise>  <!-- This is a check on a non-backsight point -->
        <xsl:variable name="origPtObs">
          <!-- Locate all the observations that have the same station and backsight -->
          <!-- references, are not deleted, are to the same point name, are not     -->
          <!-- check observations and are on the same face                          -->
          <xsl:for-each select="key('ptFromStn-search', StationID)">
            <xsl:if test="(Deleted = 'false') and ($bsID = BackBearingID) and
                          ($nameStr = Name) and (Classification != 'Check') and
                          ($face = Circle/Face)">
              <xsl:element name="obs">
                <xsl:value-of select="Circle/HorizontalCircle"/>
              </xsl:element>
            </xsl:if>
          </xsl:for-each>
        </xsl:variable>
        <!-- Now get the first observation - this will ensure         -->
        <!-- that we only have a single angle value left to work with -->
        <xsl:value-of select="msxsl:node-set($origPtObs)/obs[1] - Circle/HorizontalCircle"/>  <!-- Report delta from current obs to Orig obs -->
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
 
  <xsl:variable name="deltaHzObs">
    <xsl:variable name="absDeltaAngle" select="concat(substring('-',2 - ($deltaAngle &lt; 0)), '1') * $deltaAngle"/>
    <xsl:choose>
      <xsl:when test="$absDeltaAngle &gt; 350">  <!-- Have a value close to 360 deg -->
        <xsl:choose>
          <xsl:when test="$deltaAngle &gt; 0">
            <xsl:value-of select="$deltaAngle - 360.0"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$deltaAngle + 360.0"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$deltaAngle"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="deltaHzObsStr">
    <xsl:call-template name="FormatAngle">
      <xsl:with-param name="theAngle">
        <xsl:value-of select="$deltaHzObs"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="absHzDist">
    <xsl:if test="string(number(ObservationPolarDeltas/HorizontalDistance)) != 'NaN'">
      <xsl:value-of select="concat(substring('-',2 - (number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor) &lt; 0)), '1') * number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor)"/>
    </xsl:if>
  </xsl:variable>

  <xsl:variable name="absVtDist">
    <xsl:if test="string(number(ObservationPolarDeltas/VerticalDistance)) != 'NaN'">
      <xsl:value-of select="concat(substring('-',2 - (number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor) &lt; 0)), '1') * number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor)"/>
    </xsl:if>
  </xsl:variable>

  <xsl:variable name="highlight">
    <xsl:choose>
      <xsl:when test="(($absHzDist != '') and ($hzTolForHighlight &lt; $absHzDist)) or
                      (($absVtDist != '') and ($vtTolForHighlight &lt; $absVtDist))">true</xsl:when>
      <xsl:otherwise>false</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:if test="($bsStr != '' and $checkType = 'Backsight check shots only') or
                ($checkType = 'All conventional check shots')">
    <xsl:choose>
      <xsl:when test="$highlight = 'true'">
        <tr>
          <td class="highlightRed">  <!-- Output the station name -->
            <xsl:for-each select="key('stnID-search', StationID)">
              <xsl:value-of select="StationName"/>
            </xsl:for-each>
          </td>
          <td class="highlightRed">  <!-- Output the name of the check point -->
            <xsl:value-of select="concat(Name, $bsStr)"/>
          </td>
          <td class="highlightRed" align="right">  <!-- Output the delta horizontal angle -->
            <xsl:value-of select="$deltaHzObsStr"/>
          </td>
          <td class="highlightRed" align="right">  <!-- Output the delta horizontal distance if available -->
            <xsl:value-of select="format-number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
          <td class="highlightRed" align="right">  <!-- Output the delta vertical distance if available -->
            <xsl:value-of select="format-number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
      </xsl:when>
      <xsl:otherwise>
        <tr>
          <td class="bold">  <!-- Output the station name -->
            <xsl:for-each select="key('stnID-search', StationID)">
              <xsl:value-of select="StationName"/>
            </xsl:for-each>
          </td>
          <td class="bold">  <!-- Output the name of the check point -->
            <xsl:value-of select="concat(Name, $bsStr)"/>
          </td>
          <td class="bold" align="right">  <!-- Output the delta horizontal angle -->
            <xsl:value-of select="$deltaHzObsStr"/>
          </td>
          <td class="bold" align="right">  <!-- Output the delta horizontal distance if available -->
            <xsl:value-of select="format-number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
          <td class="bold" align="right">  <!-- Output the delta vertical distance if available -->
            <xsl:value-of select="format-number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* GNSS PointRecord Output ****************** -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="GNSS">

  <xsl:variable name="absHzDist">
    <xsl:if test="string(number(ObservationPolarDeltas/HorizontalDistance)) != 'NaN'">
      <xsl:value-of select="concat(substring('-',2 - (number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor) &lt; 0)), '1') * number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor)"/>
    </xsl:if>
  </xsl:variable>

  <xsl:variable name="absVtDist">
    <xsl:if test="string(number(ObservationPolarDeltas/VerticalDistance)) != 'NaN'">
      <xsl:value-of select="concat(substring('-',2 - (number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor) &lt; 0)), '1') * number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor)"/>
    </xsl:if>
  </xsl:variable>

  <xsl:variable name="highlight">
    <xsl:choose>
      <xsl:when test="(($absHzDist != '') and ($hzTolForHighlight &lt; $absHzDist)) or
                      (($absVtDist != '') and ($vtTolForHighlight &lt; $absVtDist))">true</xsl:when>
      <xsl:otherwise>false</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Output the point name -->
  <tr>
    <xsl:choose>
      <xsl:when test="$highlight = 'true'">
        <td class="highlightRed" align="left">
          <xsl:value-of select="Name"/>
        </td>

        <td class="highlightRed" align="right">  <!-- Output the delta horizontal distance if available -->
          <xsl:value-of select="format-number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td class="highlightRed" align="right">  <!-- Output the delta vertical distance if available -->
          <xsl:value-of select="format-number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:when>
      <xsl:otherwise>
        <td class="bold" align="left">
          <xsl:value-of select="Name"/>
        </td>

        <td class="bold" align="right">  <!-- Output the delta horizontal distance if available -->
          <xsl:value-of select="format-number(ObservationPolarDeltas/HorizontalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td class="bold" align="right">  <!-- Output the delta vertical distance if available -->
          <xsl:value-of select="format-number(ObservationPolarDeltas/VerticalDistance * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:otherwise>
    </xsl:choose>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output Angle in Appropriate Format **************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatAngle">
  <xsl:param name="theAngle"/>
  <xsl:param name="secDecPlaces" select="0"/>
  <xsl:param name="DMSOutput" select="'false'"/>  <!-- Can be used to force DMS output -->
  <xsl:param name="useSymbols" select="'true'"/>
  <xsl:param name="impliedDecimalPt" select="'false'"/>
  <xsl:param name="gonsDecPlaces" select="5"/>    <!-- Decimal places for gons output -->
  <xsl:param name="decDegDecPlaces" select="5"/>  <!-- Decimal places for decimal degrees output -->
  <xsl:param name="outputAsMilligonsOrSecs" select="'false'"/>
  <xsl:param name="outputAsMilligonsOrSecsSqrd" select="'false'"/>
  <xsl:param name="dmsSymbols">&#0176;'"</xsl:param>

  <xsl:variable name="gonsDecPl">
    <xsl:choose>
      <xsl:when test="$gonsDecPlaces = 1"><xsl:value-of select="$DecPl1"/></xsl:when>
      <xsl:when test="$gonsDecPlaces = 2"><xsl:value-of select="$DecPl2"/></xsl:when>
      <xsl:when test="$gonsDecPlaces = 3"><xsl:value-of select="$DecPl3"/></xsl:when>
      <xsl:when test="$gonsDecPlaces = 4"><xsl:value-of select="$DecPl4"/></xsl:when>
      <xsl:when test="$gonsDecPlaces = 5"><xsl:value-of select="$DecPl5"/></xsl:when>
      <xsl:when test="$gonsDecPlaces = 6"><xsl:value-of select="$DecPl6"/></xsl:when>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="decDegDecPl">
    <xsl:choose>
      <xsl:when test="$decDegDecPlaces = 1"><xsl:value-of select="$DecPl1"/></xsl:when>
      <xsl:when test="$decDegDecPlaces = 2"><xsl:value-of select="$DecPl2"/></xsl:when>
      <xsl:when test="$decDegDecPlaces = 3"><xsl:value-of select="$DecPl3"/></xsl:when>
      <xsl:when test="$decDegDecPlaces = 4"><xsl:value-of select="$DecPl4"/></xsl:when>
      <xsl:when test="$decDegDecPlaces = 5"><xsl:value-of select="$DecPl5"/></xsl:when>
      <xsl:when test="$decDegDecPlaces = 6"><xsl:value-of select="$DecPl6"/></xsl:when>
    </xsl:choose>
  </xsl:variable>

  <xsl:choose>
    <!-- Null angle value -->
    <xsl:when test="string(number($theAngle))='NaN'">
      <xsl:value-of select="format-number($theAngle, $DecPl3, 'Standard')"/> <!-- Use the defined null format output -->
    </xsl:when>
    <!-- There is an angle value -->
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="($AngleUnit = 'DMSDegrees') or not($DMSOutput = 'false')">
          <xsl:choose>
            <xsl:when test="$outputAsMilligonsOrSecs != 'false'">
              <xsl:value-of select="format-number($theAngle * $AngleConvFactor * 3600.0, '00.0', 'Standard')"/>
            </xsl:when>            
            <xsl:when test="$outputAsMilligonsOrSecsSqrd != 'false'">
              <xsl:value-of select="format-number($theAngle * $AngleConvFactor * 3600.0 * 3600.0, '00.000', 'Standard')"/>
            </xsl:when>            
            <xsl:otherwise>
              <xsl:call-template name="FormatDMSAngle">
                <xsl:with-param name="decimalAngle" select="$theAngle"/>
                <xsl:with-param name="secDecPlaces" select="$secDecPlaces"/>
                <xsl:with-param name="useSymbols" select="$useSymbols"/>
                <xsl:with-param name="impliedDecimalPt" select="$impliedDecimalPt"/>
                <xsl:with-param name="dmsSymbols" select="$dmsSymbols"/>
              </xsl:call-template>
            </xsl:otherwise>
          </xsl:choose>  
        </xsl:when>

        <xsl:otherwise>
          <xsl:variable name="fmtAngle">
            <xsl:choose>
              <xsl:when test="($AngleUnit = 'Gons') and ($DMSOutput = 'false')">
                <xsl:choose>
                  <xsl:when test="$outputAsMilligonsOrSecs != 'false'">
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor * 1000.0, $DecPl2, 'Standard')"/>
                  </xsl:when>
                  <xsl:when test="$outputAsMilligonsOrSecsSqrd != 'false'">
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor * 1000.0 * 1000.0, $DecPl4, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:choose>
                      <xsl:when test="$secDecPlaces &gt; 0">  <!-- More accurate angle output required -->
                        <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $DecPl8, 'Standard')"/>
                      </xsl:when>
                      <xsl:otherwise>
                        <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $gonsDecPl, 'Standard')"/>
                      </xsl:otherwise>
                    </xsl:choose>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:when>

              <xsl:when test="($AngleUnit = 'Mils') and ($DMSOutput = 'false')">
                <xsl:choose>
                  <xsl:when test="$secDecPlaces &gt; 0">  <!-- More accurate angle output required -->
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $DecPl6, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $DecPl4, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:when>

              <xsl:when test="($AngleUnit = 'DecimalDegrees') and ($DMSOutput = 'false')">
                <xsl:choose>
                  <xsl:when test="$secDecPlaces &gt; 0">  <!-- More accurate angle output required -->
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $DecPl8, 'Standard')"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:value-of select="format-number($theAngle * $AngleConvFactor, $decDegDecPl, 'Standard')"/>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:when>
            </xsl:choose>
          </xsl:variable>
          
          <xsl:choose>
            <xsl:when test="$impliedDecimalPt != 'true'">
              <xsl:value-of select="$fmtAngle"/>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="translate($fmtAngle, '.', '')"/>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Format a DMS Angle ********************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatDMSAngle">
  <xsl:param name="decimalAngle"/>
  <xsl:param name="secDecPlaces" select="0"/>
  <xsl:param name="useSymbols" select="'true'"/>
  <xsl:param name="impliedDecimalPt" select="'false'"/>
  <xsl:param name="dmsSymbols">&#0176;'"</xsl:param>

  <xsl:variable name="degreesSymbol">
    <xsl:choose>
      <xsl:when test="$useSymbols = 'true'"><xsl:value-of select="substring($dmsSymbols, 1, 1)"/></xsl:when>  <!-- Degrees symbol ° -->
      <xsl:otherwise>
        <xsl:if test="$impliedDecimalPt != 'true'">.</xsl:if>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="minutesSymbol">
    <xsl:choose>
      <xsl:when test="$useSymbols = 'true'"><xsl:value-of select="substring($dmsSymbols, 2, 1)"/></xsl:when>
      <xsl:otherwise></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="secondsSymbol">
    <xsl:choose>
      <xsl:when test="$useSymbols = 'true'"><xsl:value-of select="substring($dmsSymbols, 3, 1)"/></xsl:when>
      <xsl:otherwise></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="sign">
    <xsl:if test="$decimalAngle &lt; '0.0'">-1</xsl:if>
    <xsl:if test="$decimalAngle &gt;= '0.0'">1</xsl:if>
  </xsl:variable>

  <xsl:variable name="posDecimalDegrees" select="number($decimalAngle * $sign)"/>

  <xsl:variable name="positiveDecimalDegrees">  <!-- Ensure an angle very close to 360° is treated as 0° -->
    <xsl:choose>
      <xsl:when test="(360.0 - $posDecimalDegrees) &lt; 0.00001">
        <xsl:value-of select="0"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$posDecimalDegrees"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="decPlFmt">
    <xsl:choose>
      <xsl:when test="$secDecPlaces = 0"><xsl:value-of select="''"/></xsl:when>
      <xsl:when test="$secDecPlaces = 1"><xsl:value-of select="'.0'"/></xsl:when>
      <xsl:when test="$secDecPlaces = 2"><xsl:value-of select="'.00'"/></xsl:when>
      <xsl:when test="$secDecPlaces = 3"><xsl:value-of select="'.000'"/></xsl:when>
      <xsl:when test="$secDecPlaces = 4"><xsl:value-of select="'.0000'"/></xsl:when>
      <xsl:when test="$secDecPlaces = 5"><xsl:value-of select="'.00000'"/></xsl:when>
      <xsl:when test="$secDecPlaces = 6"><xsl:value-of select="'.000000'"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="''"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="degrees" select="floor($positiveDecimalDegrees)"/>
  <xsl:variable name="decimalMinutes" select="number(number($positiveDecimalDegrees - $degrees) * 60 )"/>
  <xsl:variable name="minutes" select="floor($decimalMinutes)"/>
  <xsl:variable name="seconds" select="number(number($decimalMinutes - $minutes)*60)"/>

  <xsl:variable name="partiallyNormalisedMinutes">
    <xsl:if test="number(format-number($seconds, concat('00', $decPlFmt))) = 60"><xsl:value-of select="number($minutes + 1)"/></xsl:if>
    <xsl:if test="not(number(format-number($seconds, concat('00', $decPlFmt))) = 60)"><xsl:value-of select="$minutes"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="normalisedSeconds">
    <xsl:if test="number(format-number($seconds, concat('00', $decPlFmt))) = 60"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(number(format-number($seconds, concat('00', $decPlFmt))) = 60)"><xsl:value-of select="$seconds"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="partiallyNormalisedDegrees">
    <xsl:if test="format-number($partiallyNormalisedMinutes, '0') = '60'"><xsl:value-of select="number($degrees + 1)"/></xsl:if>
    <xsl:if test="not(format-number($partiallyNormalisedMinutes, '0') = '60')"><xsl:value-of select="$degrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="normalisedDegrees">
    <xsl:if test="format-number($partiallyNormalisedDegrees, '0') = '360'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($partiallyNormalisedDegrees, '0') = '360')"><xsl:value-of select="$partiallyNormalisedDegrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="normalisedMinutes">
    <xsl:if test="format-number($partiallyNormalisedMinutes, '00') = '60'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($partiallyNormalisedMinutes, '00') = '60')"><xsl:value-of select="$partiallyNormalisedMinutes"/></xsl:if>
  </xsl:variable>

  <xsl:if test="$sign = -1">-</xsl:if>
  <xsl:value-of select="format-number($normalisedDegrees, '0')"/>
  <xsl:value-of select="$degreesSymbol"/>
  <xsl:value-of select="format-number($normalisedMinutes, '00')"/>
  <xsl:value-of select="$minutesSymbol"/>
  <xsl:choose>
    <xsl:when test="$useSymbols = 'true'">
      <xsl:value-of select="format-number($normalisedSeconds, concat('00', $decPlFmt))"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="translate(format-number($normalisedSeconds, concat('00', $decPlFmt)), '.', '')"/>
    </xsl:otherwise>
  </xsl:choose>
  <xsl:value-of select="$secondsSymbol"/>
</xsl:template>


</xsl:stylesheet>
