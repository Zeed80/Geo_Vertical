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

<xsl:output method="html" omit-xml-declaration="no" encoding="utf-8"/>

<xsl:variable name="includeHeadingLines" select="'Yes'"/>
<xsl:variable name="outputFormattedStationVals" select="'Yes'"/>

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
<xsl:variable name="userField1" select="'startDate|Optional start date for report (yyyy-mm-dd)|string'"/>
<xsl:variable name="startDate" select="''"/>
<xsl:variable name="userField2" select="'endDate|Optional end date for report (yyyy-mm-dd)|string'"/>
<xsl:variable name="endDate" select="''"/>

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

  <title>Catch Point Report</title>
  <h2>Catch Point Report</h2>

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
        <th width="15%" align="center" bgcolor="silver">Station</th>
        <th width="14%" align="center" bgcolor="silver">Catch Elev</th>
        <th width="14%" align="center" bgcolor="silver">Catch Offset</th>
        <th width="14%" align="center" bgcolor="silver">V Dist to CL</th>
        <th width="15%" align="center" bgcolor="silver">Staked Slope</th>
        <th width="14%" align="center" bgcolor="silver">Dist to hinge</th>
        <th width="14%" align="center" bgcolor="silver">V Dist to hinge</th>
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
  <!-- Process the Point records under the FieldBook node that have a staked catch point -->
  <xsl:apply-templates select="PointRecord[(Deleted = 'false') and Stakeout/CatchPoint]"/>
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
    <tr>
      <td align="right">
        <xsl:call-template name="formatStationVal">
          <xsl:with-param name="StationVal" select="Stakeout/RoadDesign/Station"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatValue">
          <xsl:with-param name="value" select="Stakeout/CatchPoint/Elevation"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatOffsetValue">
          <xsl:with-param name="value" select="Stakeout/CatchPoint/Offset"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatCutFillValue">
          <xsl:with-param name="value" select="Stakeout/CatchPointTemplateReport[last()]/DeltaElevation"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatPercentageValue">
          <xsl:with-param name="value" select="Stakeout/CatchPoint/AsStakedSideSlopeGrade"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatValue">
          <xsl:with-param name="value" select="Stakeout/CatchPointTemplateReport[1]/HorizontalDistance"/>
        </xsl:call-template>
      </td>

      <td align="right">
        <xsl:call-template name="formatCutFillValue">
          <xsl:with-param name="value" select="Stakeout/CatchPointTemplateReport[1]/DeltaElevation"/>
        </xsl:call-template>
      </td>
    </tr>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return Formatted Value with Units Identifier ********* -->
<!-- **************************************************************** -->
<xsl:template name="formatValue">
  <xsl:param name="value"/>
  <xsl:param name="withUnits" select="'false'"/>

  <xsl:value-of select="format-number($value * $DistConvFactor, $DecPl3, 'Standard')"/>
  <xsl:if test="$withUnits = 'true'">
    <!-- Now append the units abbreviation -->
    <xsl:choose>
      <xsl:when test="$DistUnit='InternationalFeet'">ift</xsl:when>
      <xsl:when test="$DistUnit='USSurveyFeet'">sft</xsl:when>
      <xsl:otherwise>m</xsl:otherwise>
    </xsl:choose>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Return Formatted Offset Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="formatOffsetValue">
  <xsl:param name="value"/>

  <xsl:variable name="sideStr">
    <xsl:choose>
      <xsl:when test="$value &lt; 0"> Left</xsl:when>
      <xsl:otherwise> Right</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Get the formatted with units absolute value of $value -->
  <xsl:call-template name="formatValue">
    <xsl:with-param name="value" select="concat(substring('-',2 - ($value &lt; 0)), '1') * $value"/>
  </xsl:call-template>
  
  <!-- Now output the offset side string -->
  <xsl:value-of select="$sideStr"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Return Formatted Vertical Distance Value ************ -->
<!-- **************************************************************** -->
<xsl:template name="formatVertDistValue">
  <xsl:param name="value"/>

  <xsl:variable name="upDownStr">
    <xsl:choose>
      <xsl:when test="$value &lt; 0"> Down</xsl:when>
      <xsl:otherwise> Up</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Get the formatted with units absolute value of $value -->
  <xsl:call-template name="formatValue">
    <xsl:with-param name="value" select="concat(substring('-',2 - ($value &lt; 0)), '1') * $value"/>
  </xsl:call-template>

  <!-- Now output the up/down string -->
  <xsl:value-of select="$upDownStr"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Cut/Fill Value **************** -->
<!-- **************************************************************** -->
<xsl:template name="formatCutFillValue">
  <xsl:param name="value"/>

  <!-- Output Cut or Fill identifier -->
  <xsl:choose>
    <xsl:when test="$value &lt; 0">Cut </xsl:when>
    <xsl:otherwise>Fill </xsl:otherwise>
  </xsl:choose>

  <!-- Get the formatted with units absolute value of $value -->
  <xsl:call-template name="formatValue">
    <xsl:with-param name="value" select="concat(substring('-',2 - ($value &lt; 0)), '1') * $value"/>
  </xsl:call-template>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********* Return Formatted Value with Units Identifier ********* -->
<!-- **************************************************************** -->
<xsl:template name="formatPercentageValue">
  <xsl:param name="value"/>

  <xsl:value-of select="format-number($value, $DecPl2, 'Standard')"/>
  <xsl:text>%</xsl:text>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return Formatted Station Value ***************** -->
<!-- **************************************************************** -->
<xsl:template name="formatStationVal">
  <xsl:param name="StationVal"/>
  <xsl:param name="definedFmt" select="''"/>

  <xsl:variable name="FormatStyle">
    <xsl:choose>
      <xsl:when test="$definedFmt = ''">
        <xsl:value-of select="/JOBFile/Environment/DisplaySettings/StationingFormat"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$definedFmt"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="StnVal" select="format-number($StationVal * $DistConvFactor, $DecPl2, 'Standard')"/>
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
<!-- *********** Pad a string to the right with spaces ************** -->
<!-- **************************************************************** -->
<xsl:template name="padRight">
  <xsl:param name="StringWidth"/>
  <xsl:param name="TheString"/>
  <xsl:choose>
    <xsl:when test="$StringWidth = '0'">
      <xsl:value-of select="normalize-space($TheString)"/> <!-- Function return value -->
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="PaddedStr" select="concat($TheString, '                                       ')"/>
      <xsl:value-of select="substring($PaddedStr, 1, $StringWidth)"/> <!-- Function return value -->
    </xsl:otherwise>
  </xsl:choose>
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


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


</xsl:stylesheet>