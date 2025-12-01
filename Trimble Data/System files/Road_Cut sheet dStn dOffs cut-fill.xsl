<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
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

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

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

<xsl:variable name="userField1" select="'ptIdentification|Point identification|stringMenu|2|Station/Offset|Point name'"/>
<xsl:variable name="ptIdentification" select="'Station/Offset'"/>
<xsl:variable name="userField2" select="'startDate|Optional start date for report (yyyy-mm-dd)|string'"/>
<xsl:variable name="startDate" select="''"/>
<xsl:variable name="userField3" select="'endDate|Optional end date for report (yyyy-mm-dd)|string'"/>
<xsl:variable name="endDate" select="''"/>

<xsl:variable name="RoadName" select="''"/>

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

<xsl:variable name="reportStartDate">
  <xsl:choose>
    <xsl:when test="$startDate = ''">
      <xsl:value-of select="substring-before(/JOBFile/FieldBook/PointRecord[(Deleted = 'false') and Stakeout][1]/@TimeStamp, 'T')"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$startDate"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="reportEndDate">
  <xsl:choose>
    <xsl:when test="$endDate = ''">
      <xsl:value-of select="substring-before(/JOBFile/FieldBook/PointRecord[(Deleted = 'false') and Stakeout][last()]/@TimeStamp, 'T')"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$endDate"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<xsl:variable name="startJulianDay">
  <xsl:call-template name="julianDay">
    <xsl:with-param name="timeStamp" select="concat($reportStartDate, 'T00:00:00')"/>
  </xsl:call-template>
</xsl:variable>

<xsl:variable name="endJulianDay">
  <xsl:call-template name="julianDay">
    <xsl:with-param name="timeStamp" select="concat($reportEndDate, 'T00:00:00')"/>
  </xsl:call-template>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>

  <title>Stakeout Report</title>
  <h2>Stakeout Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    body, table, td, th
    {
      font-size:13px;
    }
  </style>

  <head>
  </head>

  <body>
  <table border="0" width="60%" cellpadding="5">
    <tr>
      <th align="left">Job name:</th>
      <td><xsl:value-of select="JOBFile/@jobName"/></td>
    </tr>
    <xsl:for-each select="JOBFile/FieldBook/JobPropertiesRecord[last()]">
      <xsl:if test="Reference != ''">
        <tr>
          <th align="left">Job reference:</th>
          <td><xsl:value-of select="Reference"/></td>
        </tr>
      </xsl:if>
      <xsl:if test="Description != ''">
        <tr>
          <th align="left">Job description:</th>
          <td><xsl:value-of select="Description"/></td>
        </tr>
      </xsl:if>
      <xsl:if test="Operator != ''">
        <tr>
          <th align="left">Operator:</th>
          <td><xsl:value-of select="Operator"/></td>
        </tr>
      </xsl:if>
      <xsl:if test="JobNote != ''">
        <tr>
          <th align="left">Note:</th>
          <td><xsl:value-of select="JobNote"/></td>
        </tr>
      </xsl:if>
    </xsl:for-each>
    <xsl:if test="JOBFile/@TimeStamp != ''"> <!-- Date could be null in an updated job -->
      <tr>
        <th align="left">Job created on:</th>
        <td>
          <!-- Output in US format mm-dd-yy / hh:mm:ss -->
          <xsl:value-of select="substring(JOBFile/@TimeStamp, 6, 5)"/>
          <xsl:text>-</xsl:text>
          <xsl:value-of select="substring(JOBFile/@TimeStamp, 1, 4)"/>
        </td>
      </tr>
    </xsl:if>
    <tr>
      <xsl:choose>
        <xsl:when test="JOBFile/@product">
          <th align="left"><xsl:value-of select="JOBFile/@product"/> version:</th>
          <td><xsl:value-of select="JOBFile/@productVersion"/></td>
        </xsl:when>
        <xsl:otherwise>
          <th align="left"><xsl:text>Trimble Survey Controller version:</xsl:text></th>
          <td><xsl:value-of select="format-number(JOBFile/@version div 100, $DecPl2, 'Standard')"/></td>
        </xsl:otherwise>
      </xsl:choose>
    </tr>
    <tr>
      <th align="left">Distance/Coordinate units:</th>
      <td>
        <xsl:choose>
          <xsl:when test="$DistUnit='Metres'">Metres</xsl:when>
          <xsl:when test="$DistUnit='InternationalFeet'">Int. Feet</xsl:when>
          <xsl:when test="$DistUnit='USSurveyFeet'">US Survey Feet</xsl:when>
          <xsl:otherwise>Metres</xsl:otherwise>
        </xsl:choose>
      </td>
    </tr>
  </table>
  
  <xsl:call-template name="SeparatingLine"/>
  <br/>
  <table border="1" width="100%" cellpadding="2">
    <thead>
      <tr>
        <xsl:choose>
          <xsl:when test="$ptIdentification = 'Station/Offset'">
            <th width="20%" align="center">Station/Offset</th>
          </xsl:when>
          <xsl:otherwise>
            <th width="20%" align="center">Name</th>
          </xsl:otherwise>
        </xsl:choose>
        <th width="12%" align="center">Staked On</th>
        <th width="12%" align="center">Δ Station</th>
        <th width="12%" align="center">Δ Offset</th>
        <th width="12%" align="center">Cut/Fill</th>
        <th width="16%" align="center">Code</th>
        <th width="16%" align="center">Date/Time</th>
      </tr>
    </thead>
    <tbody>

    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />

    </tbody>
  </table>
  </body>
  </html>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
  <!-- Process the PointRecord elements with road stakeout data -->
  <!-- Sort points by road name then station then offset -->
  <xsl:choose>
    <xsl:when test="$RoadName = ''">  <!-- No road name specified so output points from any road -->
      <xsl:apply-templates select="PointRecord[Stakeout/RoadDesign and (Deleted = 'false')]">
        <xsl:sort data-type="text" order="ascending" select="Stakeout/RoadDesign/Name"/>
        <xsl:sort data-type="number" order="ascending" select="Stakeout/RoadDesign/Station"/>
        <xsl:sort data-type="number" order="ascending" select="(Stakeout/RoadDesign[Offset != ''] | Stakeout/CatchPoint[Offset != ''])/Offset"/>
      </xsl:apply-templates>
    </xsl:when>
    <xsl:otherwise>
      <xsl:apply-templates select="PointRecord[Stakeout/RoadDesign and (Stakeout/RoadDesign/Name = $RoadName) and (Deleted = 'false')]">
        <xsl:sort data-type="text" order="ascending" select="Stakeout/RoadDesign/Name"/>
        <xsl:sort data-type="number" order="ascending" select="Stakeout/RoadDesign/Station"/>
        <xsl:sort data-type="number" order="ascending" select="(Stakeout/RoadDesign[Offset != ''] | Stakeout/CatchPoint[Offset != ''])/Offset"/>
      </xsl:apply-templates>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord">
  <xsl:variable name="validDate">
    <xsl:call-template name="inDateRange">
      <xsl:with-param name="date" select="substring-before(@TimeStamp, 'T')"/>
    </xsl:call-template>
  </xsl:variable>

  <xsl:if test="$validDate = 'true'">
    <xsl:call-template name="StakeoutDeltas"/>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Stakeout Deltas Details Output ****************** -->
<!-- **************************************************************** -->
<xsl:template name="StakeoutDeltas">
  <xsl:variable name="dStnStr" select="format-number(Stakeout/LinearDeltas/DeltaStation * $DistConvFactor, $DecPl3, 'Standard')"/>

  <xsl:variable name="dOffsStr" select="format-number(Stakeout/LinearDeltas/DeltaOffset * $DistConvFactor, $DecPl3, 'Standard')"/>

  <xsl:variable name="dElev">
    <xsl:choose>
      <xsl:when test="Stakeout/GridDeltas/DeltaElevation != ''">
        <xsl:value-of select="Stakeout/GridDeltas/DeltaElevation"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Stakeout/LinearDeltas/DeltaElevation"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="dElevStr">
    <xsl:value-of select="format-number($dElev * $DistConvFactor, $DecPl3, 'Standard')"/>
  </xsl:variable>

  <xsl:variable name="StnValue" select="Stakeout/RoadDesign/Station"/>

  <xsl:variable name="OffsetVal">
    <xsl:choose>
      <xsl:when test="Stakeout/RoadDesign/Offset != ''">
        <xsl:value-of select="format-number(Stakeout/RoadDesign/Offset * $DistConvFactor, $DecPl3, 'Standard')"/>
      </xsl:when>
      <xsl:when test="Stakeout/CatchPoint/Offset and
                      (Stakeout/CatchPoint/Offset &gt; 0.0)">
        <xsl:value-of select="'R Catch'"/>
      </xsl:when>
      <xsl:when test="Stakeout/CatchPoint/Offset and
                      (Stakeout/CatchPoint/Offset &lt; 0.0)">
        <xsl:value-of select="'L Catch'"/>
      </xsl:when>
    </xsl:choose>
  </xsl:variable>
  
  <xsl:variable name="PtIDStr">
    <xsl:choose>
      <xsl:when test="$ptIdentification = 'Station/Offset'">
        <xsl:variable name="StnVal">
          <xsl:call-template name="FormattedStationVal">
            <xsl:with-param name="StationVal" select="$StnValue"/>
          </xsl:call-template>
        </xsl:variable>

        <xsl:value-of select="concat($StnVal, ' / ', $OffsetVal)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Name"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="dateTime">
    <!-- Output in US format mm-dd-yy / hh:mm:ss -->
    <xsl:value-of select="substring(@TimeStamp, 6, 5)"/>
    <xsl:text>-</xsl:text>
    <xsl:value-of select="substring(@TimeStamp, 3, 2)"/>
    <xsl:text> / </xsl:text>
    <xsl:value-of select="substring(@TimeStamp, 12, 8)"/>
  </xsl:variable>

  <tr>
    <td align="left"><xsl:value-of select="$PtIDStr"/></td>

    <td align="left"><xsl:value-of select="Stakeout/*/Name"/></td>

    <td align="right"><xsl:value-of select="$dStnStr"/></td>

    <td align="right"><xsl:value-of select="$dOffsStr"/></td>

    <td align="right"><xsl:value-of select="$dElevStr"/></td>

    <td align="left"><xsl:value-of select="Code"/></td>

    <td align="left"><xsl:value-of select="$dateTime"/></td>
  </tr>

</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Station Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="FormattedStationVal">
  <xsl:param name="StationVal"/>

  <xsl:variable name="FormatStyle" select="/JOBFile/Environment/DisplaySettings/StationingFormat"/>

  <xsl:variable name="StnVal" select="format-number($StationVal * $DistConvFactor, $DecPl3, 'Standard')"/>
  <xsl:variable name="SignChar">
    <xsl:choose>
      <xsl:when test="$StnVal &lt; 0.0">
        <xsl:value-of select="'-'"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="''"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="AbsStnVal" select="concat(substring('-',2 - ($StnVal &lt; 0)), '1') * $StnVal"/>

  <xsl:variable name="IntPart" select="substring-before(format-number($AbsStnVal, $DecPl3, 'Standard'), '.')"/>
  <xsl:variable name="DecPart" select="substring-after($StnVal, '.')"/>
  
  <xsl:if test="$FormatStyle = '1000.0'">
    <xsl:value-of select="$StnVal"/>
  </xsl:if>
 
  <xsl:if test="$FormatStyle = '10+00.0'">
    <xsl:choose>
      <xsl:when test="string-length($IntPart) > 2">
        <xsl:value-of select="concat($SignChar, substring($IntPart, 1, string-length($IntPart) - 2),
                                     '+', substring($IntPart, string-length($IntPart) - 1, 2), 
                                     '.', $DecPart)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="concat($SignChar, '0+', substring('00', 1, 2 - string-length($IntPart)), 
                                     $IntPart, '.', $DecPart)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>

  <xsl:if test="$FormatStyle = '1+000.0'">
    <xsl:choose>
      <xsl:when test="string-length($IntPart) > 3">
        <xsl:value-of select="concat($SignChar, substring($IntPart, 1, string-length($IntPart) - 3),
                                     '+', substring($IntPart, string-length($IntPart) - 2, 3), 
                                     '.', $DecPart)"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="concat($SignChar, '0+', substring('000', 1, 3 - string-length($IntPart)), 
                                     $IntPart, '.', $DecPart)"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******** Build up a node set of the valid output dates ********* -->
<!-- **************************************************************** -->
<xsl:template name="inDateRange">
  <xsl:param name="date"/>

  <xsl:choose>
    <xsl:when test="($startJulianDay = '') or ($endJulianDay = '')">true</xsl:when>
    <xsl:otherwise>
      <xsl:variable name="thisJulianDay">
        <xsl:call-template name="julianDay">
          <xsl:with-param name="timeStamp" select="concat($date, 'T00:00:00')"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:choose>
        <xsl:when test="($thisJulianDay &gt;= $startJulianDay) and ($thisJulianDay &lt;= $endJulianDay)">true</xsl:when>
        <xsl:otherwise>false</xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return the Julian Day for a given TimeStamp ********** -->
<!-- **************************************************************** -->
<xsl:template name="julianDay">
  <!-- The formula used in this function is valid for the years 1901 - 2099 -->
  <xsl:param name="timeStamp"/>

  <xsl:variable name="Y" select="substring($timeStamp, 1, 4)"/>
  <xsl:variable name="M" select="substring($timeStamp, 6, 2)"/>
  <xsl:variable name="D" select="substring($timeStamp, 9, 2)"/>
  <xsl:variable name="h" select="substring($timeStamp, 12, 2)"/>
  <xsl:variable name="m" select="substring($timeStamp, 15, 2)"/>
  <xsl:variable name="s" select="substring($timeStamp, 18, 2)"/>

  <xsl:value-of select="format-number(367 * $Y - floor(7 * ($Y + floor(($M + 9) div 12)) div 4) +
                                      floor(275 * $M div 9) + $D + 1721013.5 +
                                      ($h + $m div 60 + $s div 3600) div 24, '0.000000000')"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


</xsl:stylesheet>