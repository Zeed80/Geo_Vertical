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

<xsl:variable name="stationFormat" select="JOBFile/Environment/DisplaySettings/StationingFormat"/>
<xsl:variable name="gradeUnits" select="JOBFile/Environment/DisplaySettings/GradeUnits"/>

<xsl:variable name="Pi" select="3.14159265358979323846264"/>
<xsl:variable name="halfPi" select="$Pi div 2.0"/>

<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <html>

  <title>Mine Auto Stakeout Report</title>
  <h2>Mine Auto Stakeout Report</h2>

  <!-- Set the font size for use in tables -->
  <style type="text/css">
    html { font-family: Arial }
    body, table, td, th
    {
      font-size:12px;
    }
    th.blackTitleLine {background-color: black; color: white}
    th.silverTitleLine {background-color: silver}
  </style>

  <head>
  </head>

  <body>
  <table border="0" width="100%" cellpadding="5">
    <tr>
      <th align="left" width="40%">Job name</th>
      <td><xsl:value-of select="JOBFile/@jobName"/></td>
    </tr>
    <tr>
      <th align="left"><xsl:value-of select="$product"/></th>
      <td><xsl:text>v</xsl:text><xsl:value-of select="$version"/></td>
    </tr>
    <xsl:if test="JOBFile/@TimeStamp != ''"> <!-- Date could be null in an updated job -->
      <tr>
        <th align="left">Creation date</th>
        <td><xsl:value-of select="substring-before(JOBFile/@TimeStamp, 'T')"/></td>
      </tr>
    </xsl:if>
    <tr>
      <th align="left">Distance Units</th>
      <td>
        <xsl:choose>
          <xsl:when test="$DistUnit = 'InternationalFeet'">International feet</xsl:when>
          <xsl:when test="$DistUnit = 'USSurveyFeet'">US survey feet</xsl:when>
          <xsl:otherwise>Meters</xsl:otherwise>
        </xsl:choose>
      </td>
    </tr>
  </table>
  
  <xsl:call-template name="SeparatingLine"/>
  <br/>
  
  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeCenterline')]) != 0">
    <xsl:variable name="autostakeCLPts">
      <xsl:call-template name="BuildLineNodeSet">
        <xsl:with-param name="method" select="'AutostakeCenterline'"/>
      </xsl:call-template>
    </xsl:variable>

    <xsl:for-each select="msxsl:node-set($autostakeCLPts)/line">
      <table border="0" width="100%" cellpadding="2">
        <caption align="left"><font size="3"><b><xsl:text>Auto Staked Center Line Points</xsl:text></b></font></caption>
        <tr>
          <th align="left" width="40%">Start point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point1"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">End point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point2"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line azimuth:</th>
          <td align="left" width="60%">
            <xsl:call-template name="FormatAzimuth">
              <xsl:with-param name="theAzimuth" select="@lineAzimuth"/>
            </xsl:call-template>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line length:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@lineLength * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line grade:</th>
          <td align="left" width="60%">
            <xsl:choose>
              <xsl:when test="string(number(@lineGrade)) != 'NaN'">
                <xsl:call-template name="FormatGrade">
                  <xsl:with-param name="percentageGrade" select="@lineGrade"/>
                  <xsl:with-param name="gradeUnits" select="$gradeUnits"/>
                </xsl:call-template>
              </xsl:when>
              <xsl:otherwise><xsl:value-of select="format-number('', $DecPl3, 'Standard')"/></xsl:otherwise>
            </xsl:choose>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Station offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@stnOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Horizontal offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@hzOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Vertical offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@vtOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
      </table>

      <table border="1" width="100%" cellpadding="2">
        <tr>
          <th class="silverTitleLine" width="20%">Name</th>
          <th class="silverTitleLine" width="20%">Station</th>
          <th class="silverTitleLine" width="15%">Station Delta</th>
          <th class="silverTitleLine" width="15%">Hz Delta</th>
          <th class="silverTitleLine" width="15%">Vt Delta</th>
          <th class="silverTitleLine" width="15%">Delta</th>
        </tr>
        <xsl:apply-templates select="PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeCenterline')]" mode="AutostakeCenterline"/>
      </table>
      <xsl:call-template name="BlankLine"/>
    </xsl:for-each>
  </xsl:if>

  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeGradeline')]) != 0">
    <xsl:variable name="autostakeGradeLinePts">
      <xsl:call-template name="BuildLineNodeSet">
        <xsl:with-param name="method" select="'AutostakeGradeline'"/>
      </xsl:call-template>
    </xsl:variable>

    <xsl:for-each select="msxsl:node-set($autostakeGradeLinePts)/line">
      <table border="0" width="100%" cellpadding="2">
        <caption align="left"><font size="3"><b><xsl:text>Auto Staked Grade Line Points</xsl:text></b></font></caption>
        <tr>
          <th align="left" width="40%">Start point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point1"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">End point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point2"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line azimuth:</th>
          <td align="left" width="60%">
            <xsl:call-template name="FormatAzimuth">
              <xsl:with-param name="theAzimuth" select="@lineAzimuth"/>
            </xsl:call-template>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line length:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@lineLength * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line grade:</th>
          <td align="left" width="60%">
            <xsl:choose>
              <xsl:when test="string(number(@lineGrade)) != 'NaN'">
                <xsl:call-template name="FormatGrade">
                  <xsl:with-param name="percentageGrade" select="@lineGrade"/>
                  <xsl:with-param name="gradeUnits" select="$gradeUnits"/>
                </xsl:call-template>
              </xsl:when>
              <xsl:otherwise><xsl:value-of select="format-number('', $DecPl3, 'Standard')"/></xsl:otherwise>
            </xsl:choose>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Station offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@stnOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Horizontal offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@hzOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Vertical offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@vtOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
      </table>

      <table border="1" width="100%" cellpadding="2">
        <tr>
          <th class="silverTitleLine" width="20%">Name</th>
          <th class="silverTitleLine" width="20%">Station</th>
          <th class="silverTitleLine" width="15%">Station Delta</th>
          <th class="silverTitleLine" width="15%">Hz Delta</th>
          <th class="silverTitleLine" width="15%">Vt Delta</th>
          <th class="silverTitleLine" width="15%">Delta</th>
        </tr>
        <xsl:apply-templates select="PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeGradeline')]" mode="AutostakeGradeline"/>
      </table>
      <xsl:call-template name="BlankLine"/>
    </xsl:for-each>
  </xsl:if>

  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeLaserline')]) != 0">
    <table border="1" width="100%" cellpadding="2">
      <caption align="left"><font size="3"><b><xsl:text>Auto Staked Laser Line Points</xsl:text></b></font></caption>
      <tr>
        <th class="silverTitleLine" width="23%">Name</th>
        <th class="silverTitleLine" width="11%">Hz Delta</th>
        <th class="silverTitleLine" width="11%">Vt Delta</th>
        <th class="silverTitleLine" width="11%">Delta</th>
        <th class="silverTitleLine" width="22%">Line Start Pt</th>
        <th class="silverTitleLine" width="22%">Line End Pt</th>
      </tr>
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeLaserline')]" mode="AutostakeLaserline"/>
    </table>
    <xsl:call-template name="BlankLine"/>
  </xsl:if>

  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeLaserlineFromCenterline')]) != 0">
    <xsl:variable name="autostakeLaserLineFromCLPts">
      <xsl:call-template name="BuildLineNodeSet">
        <xsl:with-param name="method" select="'AutostakeLaserlineFromCenterline'"/>
      </xsl:call-template>
    </xsl:variable>

    <xsl:for-each select="msxsl:node-set($autostakeLaserLineFromCLPts)/line">
      <table border="0" width="100%" cellpadding="2">
        <caption align="left"><font size="3"><b><xsl:text>Auto Staked Laser Line Offset from CL Points</xsl:text></b></font></caption>
        <tr>
          <th align="left" width="40%">Start point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point1"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">End point:</th>
          <td align="left" width="60%">
            <xsl:value-of select="@point2"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line azimuth:</th>
          <td align="left" width="60%">
            <xsl:call-template name="FormatAzimuth">
              <xsl:with-param name="theAzimuth" select="@lineAzimuth"/>
            </xsl:call-template>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line length:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@lineLength * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Line grade:</th>
          <td align="left" width="60%">
            <xsl:choose>
              <xsl:when test="string(number(@lineGrade)) != 'NaN'">
                <xsl:call-template name="FormatGrade">
                  <xsl:with-param name="percentageGrade" select="@lineGrade"/>
                  <xsl:with-param name="gradeUnits" select="$gradeUnits"/>
                </xsl:call-template>
              </xsl:when>
              <xsl:otherwise><xsl:value-of select="format-number('', $DecPl3, 'Standard')"/></xsl:otherwise>
            </xsl:choose>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Station offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@stnOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
        <tr>
          <th align="left" width="40%">Vertical offset:</th>
          <td align="left" width="60%">
            <xsl:value-of select="format-number(@vtOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
          </td>
        </tr>
      </table>

      <table border="1" width="100%" cellpadding="2">
        <tr>
          <th class="silverTitleLine" width="20%">Name</th>
          <th class="silverTitleLine" width="20%">Station</th>
          <th class="silverTitleLine" width="20%">Hz Delta</th>
          <th class="silverTitleLine" width="20%">Vt Delta</th>
          <th class="silverTitleLine" width="20%">Delta</th>
        </tr>
        <xsl:apply-templates select="PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeLaserlineFromCenterline')]" mode="AutostakeLaserlineFromCenterline"/>
      </table>
      <xsl:call-template name="BlankLine"/>
    </xsl:for-each>
  </xsl:if>
      
  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeBlasthole')]) != 0">
    <table border="1" width="100%" cellpadding="2">
      <caption align="left"><font size="3"><b><xsl:text>Auto Staked Blast Hole Points</xsl:text></b></font></caption>
      <tr>
        <th class="silverTitleLine" width="23%">Name</th>
        <th class="silverTitleLine" width="11%">Hz Delta</th>
        <th class="silverTitleLine" width="11%">Vt Delta</th>
        <th class="silverTitleLine" width="11%">Delta</th>
        <th class="silverTitleLine" width="22%">Collar Pt</th>
        <th class="silverTitleLine" width="22%">Toe Pt</th>
      </tr>
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeBlasthole')]" mode="AutostakeBlasthole"/>
    </table>
    <xsl:call-template name="BlankLine"/>
  </xsl:if>

  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakePivotpoint')]) != 0">
    <table border="1" width="50%" cellpadding="2">
      <caption align="left"><font size="3"><b><xsl:text>Auto Staked Pivot Points</xsl:text></b></font></caption>
      <tr>
        <th class="silverTitleLine" width="35%">Name</th>
        <th class="silverTitleLine" width="30%">Delta</th>
        <th class="silverTitleLine" width="35%">Pivot Pt</th>
      </tr>
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakePivotpoint')]" mode="AutostakePivotpoint"/>
    </table>
    <xsl:call-template name="BlankLine"/>
  </xsl:if>

  <xsl:if test="count(JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeProjectline')]) != 0">
    <table border="1" width="100%" cellpadding="2">
      <caption align="left"><font size="3"><b><xsl:text>Auto Staked Project Line Points</xsl:text></b></font></caption>
      <tr>
        <th class="silverTitleLine" width="19%">Name</th>
        <th class="silverTitleLine" width="9%">Hz Offset</th>
        <th class="silverTitleLine" width="9%">Vt Offset</th>
        <th class="silverTitleLine" width="9%">Hz Delta</th>
        <th class="silverTitleLine" width="9%">Vt Delta</th>
        <th class="silverTitleLine" width="9%">Delta</th>
        <th class="silverTitleLine" width="18%">Line Start Pt</th>
        <th class="silverTitleLine" width="18%">Line End Pt</th>
      </tr>
      <xsl:apply-templates select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = 'AutostakeProjectline')]" mode="AutostakeProjectline"/>
    </table>
    <xsl:call-template name="BlankLine"/>
  </xsl:if>

  </body>
  </html>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Build line node set *********************** -->
<!-- **************************************************************** -->
<xsl:template name="BuildLineNodeSet">
  <xsl:param name="method"/>

  <xsl:for-each select="JOBFile/FieldBook/PointRecord[(Deleted = 'false') and (MiningAutostake/Method = $method)]">
    <xsl:variable name="pt1" select="MiningAutostake/Point1"/>
    <xsl:variable name="pt2" select="MiningAutostake/Point2"/>
    <xsl:if test="(position() = 1) or ($pt1 != preceding-sibling::*[1]/MiningAutostake/Point1) or ($pt2 != preceding-sibling::*[1]/MiningAutostake/Point2)">
      <xsl:variable name="lineDeltas">
        <xsl:element name="deltaN" namespace="">
          <xsl:value-of select="/JOBFile/Reductions/Point[Name = $pt1]/Grid/North - /JOBFile/Reductions/Point[Name = $pt2]/Grid/North"/>
        </xsl:element>
        <xsl:element name="deltaE" namespace="">
          <xsl:value-of select="/JOBFile/Reductions/Point[Name = $pt1]/Grid/East - /JOBFile/Reductions/Point[Name = $pt2]/Grid/East"/>
        </xsl:element>
        <xsl:element name="deltaElev" namespace="">
          <xsl:value-of select="/JOBFile/Reductions/Point[Name = $pt2]/Grid/Elevation - /JOBFile/Reductions/Point[Name = $pt1]/Grid/Elevation"/>
        </xsl:element>
      </xsl:variable>

      <xsl:element name="line" namespace="">
        <xsl:attribute name="point1" namespace="">
          <xsl:value-of select="$pt1"/>
        </xsl:attribute>
        <xsl:attribute name="point2" namespace="">
          <xsl:value-of select="$pt2"/>
        </xsl:attribute>
        <xsl:attribute name="lineAzimuth" namespace="">
          <xsl:call-template name="InverseAzimuth">
            <xsl:with-param name="deltaN" select="msxsl:node-set($lineDeltas)/deltaN"/>
            <xsl:with-param name="deltaE" select="msxsl:node-set($lineDeltas)/deltaE"/>
          </xsl:call-template>
        </xsl:attribute>
        <xsl:variable name="lineLength">
          <xsl:call-template name="InverseDistance">
            <xsl:with-param name="deltaN" select="msxsl:node-set($lineDeltas)/deltaN"/>
            <xsl:with-param name="deltaE" select="msxsl:node-set($lineDeltas)/deltaE"/>
          </xsl:call-template>
        </xsl:variable>
        <xsl:attribute name="lineLength" namespace="">
          <xsl:value-of select="$lineLength"/>
        </xsl:attribute>
        <xsl:attribute name="lineGrade" namespace="">
          <xsl:value-of select="msxsl:node-set($lineDeltas)/deltaElev div $lineLength * 100.0"/>  <!-- As a percentage -->
        </xsl:attribute>
        <xsl:attribute name="stnOffset" namespace="">
          <xsl:value-of select="MiningAutostake/StationOffset"/>
        </xsl:attribute>
        <xsl:attribute name="hzOffset" namespace="">
          <xsl:value-of select="MiningAutostake/HorizontalOffset"/>
        </xsl:attribute>
        <xsl:attribute name="vtOffset" namespace="">
          <xsl:value-of select="MiningAutostake/VerticalOffset"/>
        </xsl:attribute>
        <xsl:copy-of select="."/>
        <xsl:for-each select="following-sibling::*[(MiningAutostake/Point1 = $pt1) or (MiningAutostake/Point2 = $pt2)]">
          <xsl:copy-of select="."/>
        </xsl:for-each>
      </xsl:element>
    </xsl:if>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeCenterline">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>
    
    <td align="right">  <!-- Station column -->
      <xsl:call-template name="FormatStationVal">
        <xsl:with-param name="stationVal" select="MiningAutostake/Station"/>
        <xsl:with-param name="definedFmt" select="$stationFormat"/>
      </xsl:call-template>
    </td>
    
    <td align="right">  <!-- Station delta column -->
      <xsl:value-of select="format-number(MiningAutostake/StationDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <xsl:choose>
      <xsl:when test="/JOBFile/@version &lt; 5.56">
        <td align="right">  <!-- Horizontal delta column -->
          <xsl:value-of select="format-number(MiningAutostake/HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td align="right">  <!-- Vertical delta column -->
          <xsl:value-of select="format-number(MiningAutostake/VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:when>

      <xsl:otherwise>
        <td align="right">  <!-- Horizontal delta column -->
          <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td align="right">  <!-- Vertical delta column -->
          <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:otherwise>
    </xsl:choose>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeGradeline">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Station column -->
      <xsl:call-template name="FormatStationVal">
        <xsl:with-param name="stationVal" select="MiningAutostake/Station"/>
        <xsl:with-param name="definedFmt" select="$stationFormat"/>
      </xsl:call-template>
    </td>

    <td align="right">  <!-- Station delta column -->
      <xsl:value-of select="format-number(MiningAutostake/StationDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <xsl:choose>
      <xsl:when test="/JOBFile/@version &lt; 5.56">
        <td align="right">  <!-- Horizontal delta column -->
          <xsl:value-of select="format-number(MiningAutostake/HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td align="right">  <!-- Vertical delta column -->
          <xsl:value-of select="format-number(MiningAutostake/VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:when>

      <xsl:otherwise>
        <td align="right">  <!-- Horizontal delta column -->
          <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>

        <td align="right">  <!-- Vertical delta column -->
          <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </td>
      </xsl:otherwise>
    </xsl:choose>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeLaserline">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Horizontal delta column -->
      <xsl:choose>
        <xsl:when test="/JOBFile/@version &lt; 5.56">
          <xsl:value-of select="format-number(MiningAutostake/HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="right">  <!-- Vertical delta column -->
      <xsl:choose>
        <xsl:when test="/JOBFile/@version &lt; 5.56">
          <xsl:value-of select="format-number(MiningAutostake/VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="left">  <!-- Line start point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point1 != ''">
          <xsl:value-of select="MiningAutostake/Point1"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="left">  <!-- Line end point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point2 != ''">
          <xsl:value-of select="MiningAutostake/Point2"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>
  </tr>
</xsl:template>

    
<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeLaserlineFromCenterline">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Station column -->
      <xsl:call-template name="FormatStationVal">
        <xsl:with-param name="stationVal" select="MiningAutostake/Station"/>
        <xsl:with-param name="definedFmt" select="$stationFormat"/>
      </xsl:call-template>
    </td>

    <td align="right">  <!-- Horizontal delta column -->
      <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Vertical delta column -->
      <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>
  </tr>
</xsl:template>
 

<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeBlasthole">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Horizontal delta column -->
      <xsl:choose>
        <xsl:when test="/JOBFile/@version &lt; 5.56">
          <xsl:value-of select="format-number(MiningAutostake/HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="right">  <!-- Vertical delta column -->
      <xsl:choose>
        <xsl:when test="/JOBFile/@version &lt; 5.56">
          <xsl:value-of select="format-number(MiningAutostake/VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="left">  <!-- Line start point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point1 != ''">
          <xsl:value-of select="MiningAutostake/Point1"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="left">  <!-- Line end point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point2 != ''">
          <xsl:value-of select="MiningAutostake/Point2"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakePivotpoint">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="left">  <!-- Line start point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point1 != ''">
          <xsl:value-of select="MiningAutostake/Point1"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord" mode="AutostakeProjectline">

  <tr>
    <td align="left">  <!-- Name column -->
      <xsl:value-of select="Name"/>
    </td>

    <td align="right">  <!-- Horizontal offset column -->
      <xsl:value-of select="format-number(MiningAutostake/HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Vertical offset column -->
      <xsl:value-of select="format-number(MiningAutostake/VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Horizontal delta column -->
      <xsl:value-of select="format-number(MiningAutostake/HorizontalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Vertical delta column -->
      <xsl:value-of select="format-number(MiningAutostake/VerticalDelta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="right">  <!-- Delta column -->
      <xsl:value-of select="format-number(MiningAutostake/Delta * $DistConvFactor, $DecPl3, 'Standard')"/>
    </td>

    <td align="left">  <!-- Line start point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point1 != ''">
          <xsl:value-of select="MiningAutostake/Point1"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>

    <td align="left">  <!-- Line end point column -->
      <xsl:choose>
        <xsl:when test="MiningAutostake/Point2 != ''">
          <xsl:value-of select="MiningAutostake/Point2"/>
        </xsl:when>
        <xsl:otherwise>&#160;</xsl:otherwise>
      </xsl:choose>
    </td>
  </tr>
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Blank Line Output *********************** -->
<!-- **************************************************************** -->
<xsl:template name="BlankLine">
  <br/>
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

      <xsl:if test="$zoneVal != ''">
        <xsl:value-of select="':'"/>
        <xsl:value-of select="format-number($zoneVal,'0')"/>
      </xsl:if>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output Azimuth in Appropriate Format ************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatAzimuth">
  <xsl:param name="theAzimuth"/>
  <xsl:param name="secDecPlaces" select="0"/>
  <xsl:param name="DMSOutput" select="'false'"/>  <!-- Can be used to force DMS output -->
  <xsl:param name="useSymbols" select="'true'"/>
  <xsl:param name="quadrantBearings" select="'false'"/>  <!-- Can be used to force quadrant bearing output -->
  <xsl:param name="impliedDecimalPt" select="'false'"/>
  <xsl:param name="northLbl" select="'N'"/>
  <xsl:param name="eastLbl" select="'E'"/>
  <xsl:param name="southLbl" select="'S'"/>
  <xsl:param name="westLbl" select="'W'"/>
  <xsl:param name="dmsSymbols">&#0176;'"</xsl:param>

  <xsl:choose>
    <xsl:when test="(/JOBFile/Environment/DisplaySettings/AzimuthFormat = 'QuadrantBearings') or ($quadrantBearings != 'false')">
      <xsl:call-template name="FormatQuadrantBearing">
        <xsl:with-param name="decimalAngle" select="$theAzimuth"/>
        <xsl:with-param name="secDecPlaces" select="$secDecPlaces"/>
        <xsl:with-param name="impliedDecimalPt" select="$impliedDecimalPt"/>
        <xsl:with-param name="northLbl" select="$northLbl"/>
        <xsl:with-param name="eastLbl" select="$eastLbl"/>
        <xsl:with-param name="southLbl" select="$southLbl"/>
        <xsl:with-param name="westLbl" select="$westLbl"/>
        <xsl:with-param name="dmsSymbols" select="$dmsSymbols"/>
      </xsl:call-template>
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="FormatAngle">
        <xsl:with-param name="theAngle" select="$theAzimuth"/>
        <xsl:with-param name="secDecPlaces" select="$secDecPlaces"/>
        <xsl:with-param name="DMSOutput" select="$DMSOutput"/>
        <xsl:with-param name="useSymbols" select="$useSymbols"/>
        <xsl:with-param name="impliedDecimalPt" select="$impliedDecimalPt"/>
        <xsl:with-param name="dmsSymbols" select="$dmsSymbols"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Return Formatted Grade Value ****************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatGrade">
  <xsl:param name="percentageGrade"/>
  <xsl:param name="gradeUnits" select="'Percentage'"/>
  <xsl:param name="decPlaces" select="$DecPl2"/>

  <xsl:variable name="absValue" select="concat(substring('-',2 - ($percentageGrade &lt; 0)), '1') * $percentageGrade"/>

  <xsl:choose>
    <xsl:when test="$gradeUnits = 'RatioRiseRun'">
      <xsl:if test="$percentageGrade &lt; '0.0'">-1:</xsl:if>
      <xsl:if test="$percentageGrade &gt;= '0.0'">1:</xsl:if>
      <xsl:value-of select="format-number(number(100 div $absValue), $decPlaces, 'Standard')"/>
    </xsl:when>

    <xsl:when test="$gradeUnits = 'RatioRunRise'">
      <xsl:value-of select="format-number(number(100 div $absValue), $decPlaces, 'Standard')"/>
      <xsl:if test="$percentageGrade &lt; '0.0'">:-1</xsl:if>
      <xsl:if test="$percentageGrade &gt;= '0.0'">:1</xsl:if>
    </xsl:when>

    <xsl:otherwise>  <!-- Output as percentage grade if set to Percentage or Angle -->
      <xsl:value-of select="format-number($percentageGrade, $decPlaces, 'Standard')"/>
      <xsl:text>%</xsl:text>
    </xsl:otherwise>
  </xsl:choose>
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
<!-- ******************* Compute Inverse Azimuth ******************** -->
<!-- **************************************************************** -->
<xsl:template name="InverseAzimuth">
  <xsl:param name="deltaN"/>
  <xsl:param name="deltaE"/>
  <xsl:param name="returnInRadians" select="'false'"/>

  <!-- Compute the inverse azimuth from the deltas -->
  <xsl:variable name="absDeltaN" select="concat(substring('-',2 - ($deltaN &lt; 0)), '1') * $deltaN"/>
  <xsl:variable name="absDeltaE" select="concat(substring('-',2 - ($deltaE &lt; 0)), '1') * $deltaE"/>

  <xsl:variable name="flag">
    <xsl:choose>
      <xsl:when test="$absDeltaE &gt; $absDeltaN">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="adjDeltaN">
    <xsl:choose>
      <xsl:when test="$flag"><xsl:value-of select="$absDeltaE"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="$absDeltaN"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="adjDeltaE">
    <xsl:choose>
      <xsl:when test="$flag"><xsl:value-of select="$absDeltaN"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="$absDeltaE"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Compute the raw angle value -->
  <xsl:variable name="angle">
    <xsl:choose>
      <xsl:when test="$adjDeltaN &lt; 0.000001">
        <xsl:value-of select="0"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:variable name="arcTanAngle">
          <xsl:call-template name="ArcTanSeries">
            <xsl:with-param name="tanVal" select="$adjDeltaE div $adjDeltaN"/>
          </xsl:call-template>
        </xsl:variable>
        <xsl:choose>
          <xsl:when test="$flag">
            <xsl:value-of select="$halfPi - $arcTanAngle"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$arcTanAngle"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Assemble the raw angle value into an azimuth -->
  <xsl:variable name="azimuth">
    <xsl:choose>
      <xsl:when test="$deltaE &lt; 0">
        <xsl:choose>
          <xsl:when test="$deltaN &lt; 0">
            <xsl:value-of select="$Pi + $angle"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$Pi * 2 - $angle"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:when>
      <xsl:otherwise>
        <xsl:choose>
          <xsl:when test="$deltaN &lt; 0">
            <xsl:value-of select="$Pi - $angle"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$angle"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Return the azimuth value in radians or decimal degrees as requested -->
  <xsl:choose>
    <xsl:when test="$returnInRadians = 'true'">
      <xsl:value-of select="$azimuth"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="$azimuth * 180 div $Pi"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************* Format a Quadrant Bearing ****************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatQuadrantBearing">
  <xsl:param name="decimalAngle"/>
  <xsl:param name="secDecPlaces" select="0"/>
  <xsl:param name="impliedDecimalPt" select="'false'"/>
  <xsl:param name="northLbl" select="'N'"/>
  <xsl:param name="eastLbl" select="'E'"/>
  <xsl:param name="southLbl" select="'S'"/>
  <xsl:param name="westLbl" select="'W'"/>
  <xsl:param name="dmsSymbols">&#0176;'"</xsl:param>

  <xsl:choose>
    <!-- Null azimuth value -->
    <xsl:when test="string(number($decimalAngle)) = 'NaN'">
      <xsl:value-of select="format-number($decimalAngle, $DecPl3, 'Standard')"/>  <!-- Use the defined null format output -->
    </xsl:when>
    <!-- There is an azimuth value -->
    <xsl:otherwise>
      <xsl:variable name="quadrantAngle">
        <xsl:if test="($decimalAngle &lt;= 90.0)">
          <xsl:value-of select="number ( $decimalAngle )"/>
        </xsl:if>
        <xsl:if test="($decimalAngle &gt; 90.0) and ($decimalAngle &lt;= 180.0)">
          <xsl:value-of select="number( 180.0 - $decimalAngle )"/>
        </xsl:if>
        <xsl:if test="($decimalAngle &gt; 180.0) and ($decimalAngle &lt; 270.0)">
          <xsl:value-of select="number( $decimalAngle - 180.0 )"/>
        </xsl:if>
        <xsl:if test="($decimalAngle &gt;= 270.0) and ($decimalAngle &lt;= 360.0)">
          <xsl:value-of select="number( 360.0 - $decimalAngle )"/>
        </xsl:if>
      </xsl:variable>

      <xsl:variable name="quadrantPrefix">
        <xsl:if test="($decimalAngle &lt;= 90.0) or ($decimalAngle &gt;= 270.0)"><xsl:value-of select="$northLbl"/></xsl:if>
        <xsl:if test="($decimalAngle &gt; 90.0) and ($decimalAngle &lt; 270.0)"><xsl:value-of select="$southLbl"/></xsl:if>
      </xsl:variable>

      <xsl:variable name="quadrantSuffix">
        <xsl:if test="($decimalAngle &lt;= 180.0)"><xsl:value-of select="$eastLbl"/></xsl:if>
        <xsl:if test="($decimalAngle &gt; 180.0)"><xsl:value-of select="$westLbl"/></xsl:if>
      </xsl:variable>

      <xsl:value-of select="$quadrantPrefix"/>
      <xsl:choose>
        <xsl:when test="$AngleUnit = 'DMSDegrees'">
          <xsl:call-template name="FormatDMSAngle">
            <xsl:with-param name="decimalAngle" select="$quadrantAngle"/>
            <xsl:with-param name="secDecPlaces" select="$secDecPlaces"/>
            <xsl:with-param name="impliedDecimalPt" select="$impliedDecimalPt"/>
            <xsl:with-param name="dmsSymbols" select="$dmsSymbols"/>
          </xsl:call-template>
        </xsl:when>
        <xsl:otherwise>
          <xsl:call-template name="FormatAngle">
            <xsl:with-param name="theAngle" select="$quadrantAngle"/>
            <xsl:with-param name="secDecPlaces" select="$secDecPlaces"/>
            <xsl:with-param name="impliedDecimalPt" select="$impliedDecimalPt"/>
            <xsl:with-param name="dmsSymbols" select="$dmsSymbols"/>
          </xsl:call-template>
        </xsl:otherwise>
      </xsl:choose>
      <xsl:value-of select="$quadrantSuffix"/>
    </xsl:otherwise>
  </xsl:choose>
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
